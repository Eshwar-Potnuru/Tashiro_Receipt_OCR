"""
HQ Master Ledger Writer (Phase 13)

This module provides the Graph API-based writer for the HQ Master Ledger,
which consolidates receipts from all office locations for month-end reporting.

Key Features:
    - Uses Graph API for all Excel operations (like format2_writer_graph.py)
    - ETag-based optimistic locking via conflict_resolver.safe_write()
    - Aggregates data from multiple offices into a single consolidated ledger
    - Includes office_id column for source tracking
    - Audit logging for every row written

Column Structure (HQ Master Ledger):
    A: 事業所 (Office/Location ID)
    B: 支払日 (Payment Date)
    C: 摘要 (Description - vendor/memo)
    D: 担当者 (Staff Name)
    E: 支出 (Expense Amount)
    F: インボイス (Invoice Flag - 有/無)
    G: 勘定科目 (Account Title)
    H: 10%税込額 (10% Tax Amount)
    I: 8%税込額 (8% Tax Amount)
    J: Batch ID (for tracking)

Usage:
    from app.services.hq_master_ledger_writer import write_hq_row, HQWriteResult
    
    result = write_hq_row(
        receipt_data={...},
        batch_id="abc-123",
        year=2026,
        month=3,
        user_id="admin"
    )

Author: Phase 13 - Office Month-End Send to HQ
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from app.config.onedrive_structure import (
    get_hq_folder_path,
    get_hq_master_ledger_path,
    get_hq_template_path,
    get_hq_month_sheet_name,
    get_template_sheet_name,
)
from app.services.writer_preconditions import (
    validate_year_month,
    check_sheet_exists_or_fail,
    build_error_result,
    InvalidYearMonthError,
    SheetNotFoundStrictError,
)
from app.services.graph_client import GraphAPIError
from app.services.graph_auth import is_graph_fully_configured
from app.services.onedrive_file_manager import (
    ensure_folder,
    file_exists,
    get_file_id,
    get_file_metadata,
    OneDriveFileNotFoundError,
)
from app.services.excel_reader import (
    get_worksheet_names,
    read_worksheet,
    WorksheetNotFoundError,
)
from app.services.excel_writer import (
    update_range,
    ETagConflictError,
    ExcelWriteError,
)
from app.services.conflict_resolver import (
    safe_write,
    WriteConflictError,
    LockTimeoutError,
)


logger = logging.getLogger(__name__)


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class HQWriteResult:
    """Result of a single HQ Master Ledger row write."""
    status: str  # "written", "error", "skipped_*"
    draft_id: Optional[str] = None
    office_id: Optional[str] = None
    sheet: Optional[str] = None
    row: Optional[int] = None
    batch_id: Optional[str] = None
    error: Optional[str] = None
    file_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# =============================================================================
# EXCEPTIONS
# =============================================================================

class HQWriteError(Exception):
    """Raised when HQ Master Ledger write operation fails."""
    
    def __init__(self, operation: str, message: str, batch_id: Optional[str] = None):
        self.operation = operation
        self.batch_id = batch_id
        self.message = f"HQ write error ({operation}): {message}"
        super().__init__(self.message)


class HQFileNotFoundError(HQWriteError):
    """Raised when the HQ Master Ledger file doesn't exist on OneDrive."""
    
    def __init__(self, file_path: str):
        super().__init__(
            operation="get_file",
            message=f"HQ Master Ledger file not found: {file_path}"
        )
        self.file_path = file_path


class HQSheetNotFoundError(HQWriteError):
    """Raised when the target month sheet doesn't exist."""
    
    def __init__(self, sheet_name: str):
        super().__init__(
            operation="get_sheet",
            message=f"Month sheet not found: {sheet_name}"
        )
        self.sheet_name = sheet_name


# =============================================================================
# COLUMN MAPPING CONSTANTS
# =============================================================================

# HQ Master Ledger column indices (0-based)
HQ_COLUMN_MAPPING = {
    "office_id": 0,       # A: 事業所
    "date": 1,            # B: 支払日
    "description": 2,     # C: 摘要
    "staff": 3,           # D: 担当者
    "expense": 4,         # E: 支出
    "invoice_flag": 5,    # F: インボイス
    "account": 6,         # G: 勘定科目
    "tax_10": 7,          # H: 10%税込額
    "tax_8": 8,           # I: 8%税込額
    "batch_id": 9,        # J: Batch ID
}

# Data row start (1-indexed for Excel)
HQ_DATA_START_ROW = 3  # Row 3 (header in rows 1-2)
HQ_DATA_START_ROW_0INDEXED = 2

# Key columns to check for empty row detection
HQ_KEY_COLUMNS = [0, 1, 2, 4]  # office_id, date, description, expense

# Footer detection keywords
FOOTER_KEYWORDS = ["合計", "残高", "Total"]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _column_letter(index: int) -> str:
    """Convert 0-indexed column number to Excel letter (A, B, ... Z, AA, AB...)."""
    result = ""
    while index >= 0:
        result = chr(index % 26 + ord('A')) + result
        index = index // 26 - 1
    return result


def _safe_decimal_value(value: Optional[Decimal]) -> Optional[float]:
    """Convert Decimal to float for JSON/Graph API compatibility."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _compose_description(vendor_name: Optional[str], memo: Optional[str]) -> Optional[str]:
    """Compose description from vendor name and memo."""
    if vendor_name and memo:
        return f"{vendor_name} / {memo}"
    return vendor_name or memo


def _invoice_flag_text(has_invoice: bool) -> str:
    """Return invoice presence flag (有/無)."""
    return "有" if has_invoice else "無"


# =============================================================================
# FILE MANAGEMENT
# =============================================================================

def get_hq_file_id() -> str:
    """
    Get the OneDrive file ID for the HQ Master Ledger.
    
    Returns:
        str: OneDrive file item ID
        
    Raises:
        HQFileNotFoundError: If file doesn't exist on OneDrive
    """
    file_path = get_hq_master_ledger_path()
    
    try:
        file_id = get_file_id(file_path)
        logger.debug(f"Found HQ Master Ledger file ID: {file_id[:20]}...")
        return file_id
    except OneDriveFileNotFoundError:
        raise HQFileNotFoundError(file_path)


def ensure_hq_file_exists() -> str:
    """
    Ensure the HQ Master Ledger file exists on OneDrive, creating from template if needed.
    
    Returns:
        str: OneDrive file item ID
        
    Raises:
        HQWriteError: If file creation fails
    """
    file_path = get_hq_master_ledger_path()
    
    # Check if file already exists
    if file_exists(file_path):
        return get_file_id(file_path)
    
    # Ensure HQ folder exists
    folder_path = get_hq_folder_path()
    try:
        ensure_folder(folder_path)
    except Exception as e:
        raise HQWriteError(
            operation="ensure_folder",
            message=f"Failed to create HQ folder: {e}"
        )
    
    # Copy template to create new HQ file
    template_path = get_hq_template_path()
    
    try:
        from app.services.onedrive_file_manager import copy_file
        
        from app.config.onedrive_structure import HQ_MASTER_LEDGER_NAME
        result = copy_file(template_path, folder_path, HQ_MASTER_LEDGER_NAME)
        
        file_id = result.get("id")
        logger.info(f"Created new HQ Master Ledger from template: {file_path}")
        return file_id
        
    except Exception as e:
        raise HQWriteError(
            operation="copy_template",
            message=f"Failed to create HQ file from template: {e}"
        )


# =============================================================================
# WORKSHEET OPERATIONS
# =============================================================================

def _get_or_create_month_sheet(file_id: str, year: int, month: int, etag: str) -> tuple:
    """
    Get or create the target month sheet in HQ Master Ledger.
    
    Uses "YYYY年M月" sheet naming convention (same as Format②).
    
    Args:
        file_id: OneDrive file item ID
        year: Target year
        month: Target month (1-12)
        etag: Current ETag for write operations
        
    Returns:
        tuple: (sheet_name, etag)
        
    Raises:
        HQWriteError: If sheet creation fails
    """
    target_sheet = get_hq_month_sheet_name(year, month)
    
    # Check if sheet already exists
    existing_sheets = get_worksheet_names(file_id)
    
    # Build alias patterns for flexible matching
    aliases = [
        target_sheet,                          # "2026年3月"
        f"{year}年{month}月分",                # "2026年3月分"
        f"{year}年{month}月度",                # "2026年3月度"
        f"{year}{month:02d}",                  # "202603"
        f"{year}-{month:02d}",                 # "2026-03"
    ]
    
    normalized_aliases = ["".join(a.split()) for a in aliases]
    
    for sheet in existing_sheets:
        normalized_sheet = "".join(sheet.split())
        if normalized_sheet in normalized_aliases:
            logger.debug(f"Found existing HQ month sheet: {sheet}")
            return (sheet, etag)
    
    # Sheet doesn't exist - check strict mode
    template_sheet = get_template_sheet_name()
    
    if template_sheet not in existing_sheets:
        template_sheet = existing_sheets[0] if existing_sheets else None
        if not template_sheet:
            raise HQWriteError(
                operation="create_month_sheet",
                message="No template sheet found in HQ workbook"
            )
    
    # Check strict mode before fallback
    check_sheet_exists_or_fail(target_sheet, existing_sheets, format_type="HQ")
    
    # FALLBACK (only reached if STRICT mode is off)
    logger.warning(
        f"HQ SHEET FALLBACK: Target month sheet '{target_sheet}' not found. "
        f"Available sheets: {existing_sheets}. "
        f"FALLING BACK to template sheet '{template_sheet}'."
    )
    
    return (template_sheet, etag)


def _find_next_empty_row(file_id: str, worksheet_name: str) -> int:
    """
    Find the first empty row in the HQ worksheet for data entry.
    
    Args:
        file_id: OneDrive file item ID
        worksheet_name: Name of the worksheet
        
    Returns:
        int: 1-indexed row number for the next empty row
        
    Raises:
        HQWriteError: If operation fails
    """
    try:
        rows = read_worksheet(file_id, worksheet_name, include_empty_rows=True)
        
        if not rows:
            return HQ_DATA_START_ROW
        
        # Find footer row
        footer_row = None
        for row_idx, row in enumerate(rows):
            for cell in row:
                if cell and isinstance(cell, str):
                    cell_stripped = cell.strip()
                    if any(keyword in cell_stripped for keyword in FOOTER_KEYWORDS):
                        footer_row = row_idx + 1
                        logger.debug(f"Found footer at row {footer_row}")
                        break
            if footer_row:
                break
        
        if not footer_row:
            footer_row = len(rows) + 50
        
        # Scan for first empty row in key columns
        for row_idx in range(HQ_DATA_START_ROW_0INDEXED, footer_row - 1):
            if row_idx >= len(rows):
                return row_idx + 1
            
            row = rows[row_idx]
            is_empty = True
            
            for col in HQ_KEY_COLUMNS:
                if col < len(row):
                    val = row[col]
                    if val is not None and str(val).strip() != "":
                        is_empty = False
                        break
            
            if is_empty:
                logger.debug(f"Found empty row at {row_idx + 1}")
                return row_idx + 1
        
        # No empty row found, write before footer
        next_row = footer_row - 1
        logger.warning(f"No empty rows found, writing at {next_row}")
        return next_row
        
    except WorksheetNotFoundError:
        raise HQWriteError(
            operation="find_empty_row",
            message=f"Worksheet '{worksheet_name}' not found"
        )
    except Exception as e:
        raise HQWriteError(
            operation="find_empty_row",
            message=str(e)
        )


# =============================================================================
# ROW WRITING
# =============================================================================

def _prepare_hq_row_values(
    receipt_data: Dict[str, Any],
    batch_id: str,
    staff_display: Optional[str] = None
) -> List[Any]:
    """
    Prepare row values array from receipt data for HQ Master Ledger.
    
    Column mapping (HQ Master):
        A (0): 事業所 (office_id)
        B (1): 支払日
        C (2): 摘要
        D (3): 担当者
        E (4): 支出
        F (5): インボイス
        G (6): 勘定科目
        H (7): 10%税込額
        I (8): 8%税込額
        J (9): Batch ID
    
    Args:
        receipt_data: Receipt data dictionary
        batch_id: Transfer batch identifier
        staff_display: Staff display name (optional)
        
    Returns:
        list: Array of 10 values (columns A through J)
    """
    row = [None] * 10
    
    # A: 事業所
    row[HQ_COLUMN_MAPPING["office_id"]] = receipt_data.get("business_location_id")
    
    # B: 支払日
    row[HQ_COLUMN_MAPPING["date"]] = receipt_data.get("receipt_date")
    
    # C: 摘要
    description = _compose_description(
        receipt_data.get("vendor_name"),
        receipt_data.get("memo")
    )
    row[HQ_COLUMN_MAPPING["description"]] = description
    
    # D: 担当者
    if staff_display:
        row[HQ_COLUMN_MAPPING["staff"]] = staff_display
    else:
        row[HQ_COLUMN_MAPPING["staff"]] = receipt_data.get("staff_name")
    
    # E: 支出
    total = receipt_data.get("total_amount")
    row[HQ_COLUMN_MAPPING["expense"]] = _safe_decimal_value(total)
    
    # F: インボイス有無
    has_invoice = bool(receipt_data.get("invoice_number"))
    row[HQ_COLUMN_MAPPING["invoice_flag"]] = _invoice_flag_text(has_invoice)
    
    # G: 勘定科目
    row[HQ_COLUMN_MAPPING["account"]] = receipt_data.get("account_title")
    
    # H: 10%税込額
    tax_10 = receipt_data.get("tax_10_amount")
    row[HQ_COLUMN_MAPPING["tax_10"]] = _safe_decimal_value(tax_10)
    
    # I: 8%税込額
    tax_8 = receipt_data.get("tax_8_amount")
    row[HQ_COLUMN_MAPPING["tax_8"]] = _safe_decimal_value(tax_8)
    
    # J: Batch ID (for audit trail)
    row[HQ_COLUMN_MAPPING["batch_id"]] = batch_id
    
    return row


def _write_row_to_worksheet(
    file_id: str,
    worksheet_name: str,
    row_index: int,
    row_values: List[Any],
    etag: str
) -> str:
    """
    Write a row of values to the HQ worksheet.
    
    Args:
        file_id: OneDrive file item ID
        worksheet_name: Name of the worksheet
        row_index: 1-indexed row number
        row_values: Array of values to write
        etag: Current ETag
        
    Returns:
        str: New ETag after write
        
    Raises:
        ETagConflictError: If concurrent modification detected
        ExcelWriteError: If write fails
    """
    num_cols = len(row_values)
    end_col = _column_letter(num_cols - 1)
    range_address = f"A{row_index}:{end_col}{row_index}"
    
    logger.info(f"Writing HQ Master Ledger row at {worksheet_name}!{range_address}")
    
    return update_range(
        file_id=file_id,
        worksheet_name=worksheet_name,
        range_address=range_address,
        values=[row_values],
        etag=etag
    )


# =============================================================================
# PUBLIC API
# =============================================================================

def write_hq_row(
    receipt_data: Dict[str, Any],
    batch_id: str,
    year: int,
    month: int,
    user_id: str,
    staff_display: Optional[str] = None
) -> HQWriteResult:
    """
    Write a receipt row to the HQ Master Ledger on OneDrive.
    
    This is the main entry point for Phase 13 HQ writes.
    
    Args:
        receipt_data: Receipt data dictionary with keys:
            - business_location_id: Source office ID (required)
            - receipt_date: Date string (YYYY-MM-DD)
            - vendor_name: Vendor/store name
            - memo: Additional memo
            - total_amount: Total expense amount
            - invoice_number: Invoice number (for 有/無 flag)
            - tax_10_amount: 10% tax amount
            - tax_8_amount: 8% tax amount
            - account_title: Account category
            - staff_name: Staff name
            - draft_id: Source draft UUID
        batch_id: Transfer batch identifier (for audit trail)
        year: Target year
        month: Target month (1-12)
        user_id: User ID performing the operation
        staff_display: Optional override for staff display name
        
    Returns:
        HQWriteResult: Result with status, row number, errors, etc.
    """
    draft_id = str(receipt_data.get("draft_id", ""))
    office_id = receipt_data.get("business_location_id")
    
    # PRECONDITION: Verify Graph API is configured
    if not is_graph_fully_configured():
        logger.warning(
            "HQ Master Ledger writer called but Graph API not fully configured."
        )
        return HQWriteResult(
            status="skipped_graph_not_configured",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error="Graph API credentials not configured or contain placeholders"
        )
    
    # PRECONDITION: Validate year/month
    try:
        year, month = validate_year_month(year, month)
    except InvalidYearMonthError as e:
        logger.warning(f"HQ write invalid year/month: {e}")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=str(e)
        )
    
    # Validate required fields
    if not office_id:
        return HQWriteResult(
            status="skipped_missing_office_id",
            draft_id=draft_id,
            batch_id=batch_id,
            error="business_location_id required"
        )
    
    receipt_date = receipt_data.get("receipt_date")
    if not receipt_date:
        return HQWriteResult(
            status="skipped_missing_date",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error="receipt_date required"
        )
    
    try:
        # Ensure HQ file exists
        file_id = ensure_hq_file_exists()
        
        # Define write operation with ETag
        def do_write(etag: str) -> Dict[str, Any]:
            # Get or create month sheet
            sheet_name, current_etag = _get_or_create_month_sheet(
                file_id, year, month, etag
            )
            
            # Find next empty row
            empty_row = _find_next_empty_row(file_id, sheet_name)
            
            # Prepare row values
            row_values = _prepare_hq_row_values(receipt_data, batch_id, staff_display)
            
            # Write row
            new_etag = _write_row_to_worksheet(
                file_id=file_id,
                worksheet_name=sheet_name,
                row_index=empty_row,
                row_values=row_values,
                etag=current_etag
            )
            
            return {
                "status": "written",
                "draft_id": draft_id,
                "office_id": office_id,
                "sheet": sheet_name,
                "row": empty_row,
                "batch_id": batch_id,
                "file_id": file_id,
                "new_etag": new_etag,
            }
        
        # Execute with safe_write (lock + ETag retry)
        result = safe_write(
            file_id=file_id,
            operation=do_write,
            get_etag_fn=lambda: get_file_metadata(file_id)["eTag"],
            max_retries=3,
            worksheet_name=f"{year}年{month}月",
            operation_name="write_hq_row"
        )
        
        logger.info(
            f"HQ write successful: draft_id={draft_id}, office={office_id}, "
            f"sheet={result.get('sheet')}, row={result.get('row')}, batch={batch_id}"
        )
        
        return HQWriteResult(**{k: v for k, v in result.items() if k != "new_etag"})
        
    except WriteConflictError as e:
        logger.error(f"HQ write conflict: {e}")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=f"Write conflict after retries: {e}"
        )
    except LockTimeoutError as e:
        logger.error(f"HQ lock timeout: file={e.file_id[:20]}..., timeout={e.timeout_seconds}s")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=f"Could not acquire write lock within {e.timeout_seconds}s"
        )
    except SheetNotFoundStrictError as e:
        logger.error(f"HQ strict sheet check failed: {e}")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=str(e)
        )
    except HQWriteError as e:
        logger.error(f"HQ write error: {e}")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=str(e)
        )
    except GraphAPIError as e:
        logger.error(f"HQ Graph API error: {e}")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=f"Graph API error: {e.message}"
        )
    except Exception as e:
        logger.exception(f"HQ unexpected error: {e}")
        return HQWriteResult(
            status="error",
            draft_id=draft_id,
            office_id=office_id,
            batch_id=batch_id,
            error=str(e)
        )


def write_hq_batch(
    receipts: List[Dict[str, Any]],
    batch_id: str,
    year: int,
    month: int,
    user_id: str
) -> Dict[str, Any]:
    """
    Write multiple receipts to HQ Master Ledger in a batch.
    
    Processes each receipt sequentially (Graph API writes are inherently
    serialized due to ETag requirements).
    
    Args:
        receipts: List of receipt data dictionaries
        batch_id: Transfer batch identifier
        year: Target year
        month: Target month (1-12)
        user_id: User ID performing the operation
        
    Returns:
        dict: Batch result with:
            - status: "complete", "partial", "failed"
            - total: Total receipts in batch
            - written: Number successfully written
            - failed: Number that failed
            - results: List of individual HQWriteResult dicts
    """
    results = []
    written = 0
    failed = 0
    
    for receipt in receipts:
        result = write_hq_row(
            receipt_data=receipt,
            batch_id=batch_id,
            year=year,
            month=month,
            user_id=user_id
        )
        
        results.append(result.to_dict())
        
        if result.status == "written":
            written += 1
        elif result.status.startswith("error"):
            failed += 1
    
    # Determine batch status
    if failed == 0:
        batch_status = "complete"
    elif written == 0:
        batch_status = "failed"
    else:
        batch_status = "partial"
    
    logger.info(
        f"HQ batch complete: batch_id={batch_id}, status={batch_status}, "
        f"written={written}, failed={failed}, total={len(receipts)}"
    )
    
    return {
        "status": batch_status,
        "batch_id": batch_id,
        "total": len(receipts),
        "written": written,
        "failed": failed,
        "results": results
    }
