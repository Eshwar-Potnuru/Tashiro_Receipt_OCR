"""
Format① Writer Graph API Implementation (Phase 9.R.1)

This module provides the Graph API-based writer for Format① (Individual Staff Ledger),
migrating from the local openpyxl-based implementation to OneDrive via Microsoft Graph API.

Key Changes from Local Writer:
    - Uses Graph API instead of openpyxl for all Excel operations
    - Uses ETag-based optimistic locking via conflict_resolver.safe_write()
    - Files stored on OneDrive instead of local filesystem
    - All Graph API calls use graph_request_resilient for retry logic

Behavior Preserved:
    - Same column mapping (A=担当者, B=支払日, etc.)
    - Same row finding logic (find first empty row before footer)
    - Same month sheet naming convention (YYYYMM)
    - Same file naming convention ({STAFF_NAME}_{LOCATION}.xlsx)
    - Same error handling pattern (returns dict with "status" key)

Usage:
    from app.services.format1_writer_graph import write_format1_row, Format1WriteError
    
    result = write_format1_row(
        receipt_data={"staff_id": "S001", "receipt_date": "2026-02-28", ...},
        office="Aichi",
        staff="田中太郎",
        year=2026,
        month=2,
        user_id="user123"
    )

Author: Phase 9.R.1 - Format① Writer Migration
Date: 2026-02-28
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union

from app.config.onedrive_structure import (
    get_staff_folder_path,
    get_staff_file_path,
    get_staff_file_name,
    get_month_sheet_name,
    get_template_sheet_name,
    get_format1_template_path,
)
from app.services.writer_preconditions import (
    validate_year_month,
    validate_required_fields,
    check_sheet_exists_or_fail,
    build_skip_result,
    build_error_result,
    PreconditionError,
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

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class Format1WriteError(Exception):
    """
    Raised when Format① write operation fails.
    
    Attributes:
        staff: Staff ID or name
        operation: Operation that failed
        message: Human-readable error message
    """
    
    def __init__(self, staff: str, operation: str, message: str):
        self.staff = staff
        self.operation = operation
        self.message = f"Format① write error ({operation}) for {staff}: {message}"
        super().__init__(self.message)


class Format1FileNotFoundError(Format1WriteError):
    """Raised when the staff ledger file doesn't exist on OneDrive."""
    
    def __init__(self, staff: str, file_path: str):
        super().__init__(
            staff=staff,
            operation="get_file",
            message=f"Staff ledger file not found: {file_path}"
        )
        self.file_path = file_path


class Format1SheetNotFoundError(Format1WriteError):
    """Raised when the target month sheet doesn't exist."""
    
    def __init__(self, staff: str, sheet_name: str):
        super().__init__(
            staff=staff,
            operation="get_sheet",
            message=f"Month sheet not found: {sheet_name}"
        )
        self.sheet_name = sheet_name


# =============================================================================
# COLUMN MAPPING CONSTANTS
# =============================================================================

# Column indices (0-based for internal use, mapped to A=0, B=1, etc.)
# These match the existing Format① template structure

COLUMN_MAPPING = {
    "staff": 0,           # A: 担当者
    "date": 1,            # B: 支払日
    "account": 2,         # C: 勘定科目
    "description": 3,     # D: 摘要
    # E (4): 収入 - not written
    "expense": 5,         # F: 支出
    # G (6): empty - not written
    "invoice_flag": 7,    # H: インボイス (有/無)
    # I-J (8-9): not written
    "tax_10": 10,         # K: 10%税込額
    "tax_8": 11,          # L: 8%税込額
    # M (12): not written
    # N (13): formula column (tax sum) - not written
}

# Data row start (1-indexed for Excel, 0-indexed internally = 2)
DATA_START_ROW = 3  # Row 3 in Excel (1-indexed)
DATA_START_ROW_0INDEXED = 2  # 0-indexed

# Header rows to scan for column detection
HEADER_ROW_SCAN_LIMIT = 10

# Footer detection keywords
FOOTER_KEYWORDS = ["合計", "残高", "計"]


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

def get_format1_file_id(staff_name: str, location_id: str) -> str:
    """
    Get the OneDrive file ID for a staff ledger file.
    
    Args:
        staff_name: Staff member's display name
        location_id: Business location identifier
        
    Returns:
        str: OneDrive file item ID
        
    Raises:
        Format1FileNotFoundError: If file doesn't exist on OneDrive
    """
    file_path = get_staff_file_path(staff_name, location_id)
    
    try:
        file_id = get_file_id(file_path)
        logger.debug(f"Found Format① file ID for {staff_name}_{location_id}: {file_id[:20]}...")
        return file_id
    except OneDriveFileNotFoundError:
        raise Format1FileNotFoundError(staff_name, file_path)


def ensure_staff_file_exists(staff_name: str, location_id: str) -> str:
    """
    Ensure the staff ledger file exists on OneDrive, creating from template if needed.
    
    Args:
        staff_name: Staff member's display name
        location_id: Business location identifier
        
    Returns:
        str: OneDrive file item ID
        
    Raises:
        Format1WriteError: If file creation fails
    """
    file_path = get_staff_file_path(staff_name, location_id)
    
    # Check if file already exists
    if file_exists(file_path):
        return get_file_id(file_path)
    
    # Ensure folder exists
    folder_path = get_staff_folder_path()
    try:
        ensure_folder(folder_path)
    except Exception as e:
        raise Format1WriteError(
            staff=staff_name,
            operation="ensure_folder",
            message=f"Failed to create staff folder: {e}"
        )
    
    # Copy template to create new staff file
    template_path = get_format1_template_path()
    
    try:
        # Import copy_file from onedrive_file_manager
        from app.services.onedrive_file_manager import copy_file
        
        # Copy template to staff location
        file_name = get_staff_file_name(staff_name, location_id)
        result = copy_file(template_path, folder_path, file_name)
        
        file_id = result.get("id")
        logger.info(f"Created new staff ledger from template: {file_path}")
        return file_id
        
    except Exception as e:
        raise Format1WriteError(
            staff=staff_name,
            operation="copy_template",
            message=f"Failed to create staff file from template: {e}"
        )


# =============================================================================
# WORKSHEET OPERATIONS
# =============================================================================

def _get_or_create_month_sheet(file_id: str, year: int, month: int, etag: str) -> tuple:
    """
    Get or create the target month sheet.
    
    Args:
        file_id: OneDrive file item ID
        year: Target year
        month: Target month (1-12)
        etag: Current ETag for write operations
        
    Returns:
        tuple: (sheet_name, new_etag or original etag if no write needed)
        
    Raises:
        Format1WriteError: If sheet creation fails
    """
    target_sheet = get_month_sheet_name(year, month)
    
    # Check if sheet already exists
    existing_sheets = get_worksheet_names(file_id)
    
    # Normalize sheet names for comparison
    normalized_target = "".join(target_sheet.split())
    
    for sheet in existing_sheets:
        if "".join(sheet.split()) == normalized_target:
            logger.debug(f"Found existing month sheet: {sheet}")
            return (sheet, etag)
    
    # Sheet doesn't exist - need to create by copying template sheet
    template_sheet = get_template_sheet_name()
    
    # Check if template sheet exists
    if template_sheet not in existing_sheets:
        # Use first sheet as template
        template_sheet = existing_sheets[0] if existing_sheets else None
        if not template_sheet:
            raise Format1WriteError(
                staff="",
                operation="create_month_sheet",
                message="No template sheet found in workbook"
            )
    
    # Graph API doesn't support direct worksheet copy
    # Phase 11A-1: Use STRICT mode check before falling back
    # If GRAPH_WRITER_STRICT_SHEET_MODE=true, this will raise SheetNotFoundStrictError
    check_sheet_exists_or_fail(target_sheet, existing_sheets, format_type="①")
    
    # FALLBACK behavior (only reached if STRICT mode is off):
    # Data will be written to the template sheet instead of the target month sheet.
    logger.error(
        f"SHEET FALLBACK: Target month sheet '{target_sheet}' not found in workbook. "
        f"Available sheets: {existing_sheets}. "
        f"FALLING BACK to template sheet '{template_sheet}'. "
        f"Data may be written to wrong location - verify after PoC!"
    )
    
    # Return template sheet as fallback (write to existing sheet)
    # In production, this should create the sheet properly
    return (template_sheet, etag)


def _find_next_empty_row(file_id: str, worksheet_name: str) -> int:
    """
    Find the first empty row in the worksheet for data entry.
    
    Matches the logic from the original StaffLedgerWriter:
    1. Start at row 3 (data start)
    2. Check primary columns (A, B, C) for emptiness
    3. Stop before footer row (合計, 残高, 計)
    
    Args:
        file_id: OneDrive file item ID
        worksheet_name: Name of the worksheet
        
    Returns:
        int: 1-indexed row number for the next empty row
        
    Raises:
        Format1WriteError: If operation fails
    """
    try:
        # Read entire worksheet
        rows = read_worksheet(file_id, worksheet_name, include_empty_rows=True)
        
        if not rows:
            return DATA_START_ROW
        
        # Find footer row
        footer_row = None
        for row_idx, row in enumerate(rows):
            for cell in row:
                if cell and isinstance(cell, str):
                    cell_stripped = cell.strip()
                    if any(keyword in cell_stripped for keyword in FOOTER_KEYWORDS):
                        footer_row = row_idx + 1  # Convert to 1-indexed
                        logger.debug(f"Found footer at row {footer_row}")
                        break
            if footer_row:
                break
        
        if not footer_row:
            footer_row = len(rows) + 50  # No footer found, extend beyond data
        
        # Scan for first empty row in primary columns (A, B, C = indices 0, 1, 2)
        primary_cols = [0, 1, 2]
        
        for row_idx in range(DATA_START_ROW_0INDEXED, footer_row - 1):
            if row_idx >= len(rows):
                # Reached end of data, this row is empty
                return row_idx + 1  # Convert to 1-indexed
            
            row = rows[row_idx]
            is_empty = True
            
            for col in primary_cols:
                if col < len(row):
                    val = row[col]
                    if val is not None and str(val).strip() != "":
                        is_empty = False
                        break
            
            if is_empty:
                logger.debug(f"Found empty row at {row_idx + 1}")
                return row_idx + 1  # Convert to 1-indexed
        
        # No empty row found, write before footer
        next_row = footer_row - 1
        logger.warning(f"No empty rows found, writing at {next_row}")
        return next_row
        
    except WorksheetNotFoundError:
        raise Format1WriteError(
            staff="",
            operation="find_empty_row",
            message=f"Worksheet '{worksheet_name}' not found"
        )
    except Exception as e:
        raise Format1WriteError(
            staff="",
            operation="find_empty_row",
            message=str(e)
        )


# =============================================================================
# ROW WRITING
# =============================================================================

def _prepare_row_values(
    receipt_data: Dict[str, Any],
    staff_display: str
) -> List[Any]:
    """
    Prepare row values array from receipt data.
    
    Creates a list of values in the correct column order for the template.
    
    Args:
        receipt_data: Receipt data dictionary
        staff_display: Staff display name
        
    Returns:
        list: Array of 14 values (columns A through N)
    """
    # Create 14-element array (columns A through N)
    row = [None] * 14
    
    # A: 担当者
    row[COLUMN_MAPPING["staff"]] = staff_display
    
    # B: 支払日
    row[COLUMN_MAPPING["date"]] = receipt_data.get("receipt_date")
    
    # C: 勘定科目
    row[COLUMN_MAPPING["account"]] = receipt_data.get("account_title")
    
    # D: 摘要
    description = _compose_description(
        receipt_data.get("vendor_name"),
        receipt_data.get("memo")
    )
    row[COLUMN_MAPPING["description"]] = description
    
    # F: 支出
    total = receipt_data.get("total_amount")
    row[COLUMN_MAPPING["expense"]] = _safe_decimal_value(total)
    
    # H: インボイス有無
    has_invoice = bool(receipt_data.get("invoice_number"))
    row[COLUMN_MAPPING["invoice_flag"]] = _invoice_flag_text(has_invoice)
    
    # K: 10%税込額
    tax_10 = receipt_data.get("tax_10_amount")
    row[COLUMN_MAPPING["tax_10"]] = _safe_decimal_value(tax_10)
    
    # L: 8%税込額
    tax_8 = receipt_data.get("tax_8_amount")
    row[COLUMN_MAPPING["tax_8"]] = _safe_decimal_value(tax_8)
    
    return row


def _write_row_to_worksheet(
    file_id: str,
    worksheet_name: str,
    row_index: int,
    row_values: List[Any],
    etag: str
) -> str:
    """
    Write a row of values to the worksheet.
    
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
    # Build range address (A{row}:N{row})
    num_cols = len(row_values)
    end_col = _column_letter(num_cols - 1)
    range_address = f"A{row_index}:{end_col}{row_index}"
    
    logger.info(f"Writing Format① row at {worksheet_name}!{range_address}")
    
    return update_range(
        file_id=file_id,
        worksheet_name=worksheet_name,
        range_address=range_address,
        values=[row_values],  # 2D array required
        etag=etag
    )


# =============================================================================
# PUBLIC API
# =============================================================================

def write_format1_row(
    receipt_data: Dict[str, Any],
    office: str,
    staff: str,
    year: int,
    month: int,
    user_id: str
) -> Dict[str, Any]:
    """
    Write a receipt row to the Format① staff ledger on OneDrive.
    
    This is the main entry point for the Graph API-based Format① writer.
    
    Args:
        receipt_data: Receipt data dictionary with keys:
            - staff_id: Staff identifier
            - receipt_date: Date string (YYYY-MM-DD)
            - vendor_name: Vendor/store name
            - memo: Additional memo
            - total_amount: Total expense amount
            - invoice_number: Invoice number (for 有/無 flag)
            - tax_10_amount: 10% tax amount
            - tax_8_amount: 8% tax amount
            - account_title: Account category
        office: Business location/office identifier
        staff: Staff display name
        year: Target year
        month: Target month (1-12)
        user_id: User ID performing the operation
        
    Returns:
        dict: Result dictionary with keys:
            - status: "written", "error", or "skipped_*"
            - staff: Staff identifier
            - sheet: Worksheet name
            - row: Row number written
            - file_id: OneDrive file ID
            - error: Error message (if status is "error")
            
    Raises:
        Format1WriteError: If write operation fails
    """
    staff_id = receipt_data.get("staff_id")
    
    # PRECONDITION: Verify Graph API is fully configured (Step 4 refinement)
    # This prevents cryptic failures when Graph credentials are missing/placeholder
    if not is_graph_fully_configured():
        logger.warning(
            "Format① Graph writer called but Graph API not fully configured. "
            "Ensure all MS_GRAPH_* environment variables are set with real values."
        )
        return {
            "status": "skipped_graph_not_configured",
            "reason": "Graph API credentials not configured or contain placeholders",
            "staff": staff_id,
        }
    
    # PRECONDITION: Validate year/month (Phase 11A-1)
    try:
        year, month = validate_year_month(year, month)
    except InvalidYearMonthError as e:
        logger.warning(f"Format① invalid year/month: {e}")
        return build_error_result(e, staff_id, identifier_key="staff")
    
    # Validate required fields
    if not staff_id:
        return {
            "status": "skipped_missing_staff_id",
            "reason": "staff_id required",
            "receipt_id": str(receipt_data.get("receipt_id", ""))
        }
    
    try:
        # Ensure staff file exists
        file_id = ensure_staff_file_exists(staff, office)
        
        # Define write operation with ETag
        def do_write(etag: str) -> Dict[str, Any]:
            # Get or create month sheet
            sheet_name, current_etag = _get_or_create_month_sheet(
                file_id, year, month, etag
            )
            
            # Find next empty row
            empty_row = _find_next_empty_row(file_id, sheet_name)
            
            # Prepare row values
            row_values = _prepare_row_values(receipt_data, staff)
            
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
                "staff": staff_id,
                "sheet": sheet_name,
                "row": empty_row,
                "file_id": file_id,
                "new_etag": new_etag,
            }
        
        # Execute with safe_write (lock + ETag retry)
        result = safe_write(
            file_id=file_id,
            operation=do_write,
            get_etag_fn=lambda: get_file_metadata(file_id)["eTag"],
            max_retries=3,
            worksheet_name=f"{year}{month:02d}",
            operation_name="write_format1_row"
        )
        
        logger.info(
            f"Format① write successful: staff={staff_id}, "
            f"sheet={result.get('sheet')}, row={result.get('row')}"
        )
        
        return result
        
    except WriteConflictError as e:
        logger.error(f"Format① write conflict: {e}")
        return {
            "status": "error",
            "error": f"Write conflict after retries: {e}",
            "staff": staff_id,
            "failure_type": e.failure_type.value if hasattr(e, 'failure_type') and e.failure_type else "etag_conflict"
        }
    except LockTimeoutError as e:
        logger.error(f"Format① lock timeout: file={e.file_id[:20]}..., timeout={e.timeout_seconds}s")
        return {
            "status": "error",
            "error": f"Could not acquire write lock within {e.timeout_seconds}s",
            "staff": staff_id,
            "failure_type": "lock_timeout"
        }
    except SheetNotFoundStrictError as e:
        # Phase 11A-1: STRICT mode - month sheet must exist
        logger.error(f"Format① strict sheet check failed: {e}")
        return build_error_result(e, staff_id, identifier_key="staff")
    except Format1WriteError as e:
        logger.error(f"Format① write error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "staff": staff_id
        }
    except GraphAPIError as e:
        logger.error(f"Format① Graph API error: {e}")
        return {
            "status": "error",
            "error": f"Graph API error: {e.message}",
            "staff": staff_id
        }
    except Exception as e:
        logger.exception(f"Format① unexpected error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "staff": staff_id
        }


def verify_format1_write(
    file_id: str,
    worksheet_name: str,
    row_index: int,
    expected_staff: str
) -> bool:
    """
    Verify that a Format① write was successful by reading back the data.
    
    Args:
        file_id: OneDrive file item ID
        worksheet_name: Name of the worksheet
        row_index: 1-indexed row number
        expected_staff: Expected staff name in column A
        
    Returns:
        bool: True if verification passed, False otherwise
    """
    try:
        rows = read_worksheet(file_id, worksheet_name, include_empty_rows=True)
        
        if row_index - 1 >= len(rows):
            logger.warning(f"Verification failed: row {row_index} not found")
            return False
        
        row = rows[row_index - 1]
        
        # Check staff name in column A
        if len(row) > 0:
            actual_staff = row[0]
            if actual_staff and str(actual_staff).strip() == expected_staff.strip():
                logger.debug(f"Verification passed for row {row_index}")
                return True
        
        logger.warning(
            f"Verification failed: expected staff '{expected_staff}', "
            f"got '{row[0] if row else None}'"
        )
        return False
        
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return False
