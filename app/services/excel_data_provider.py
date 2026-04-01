"""
Excel Data Provider (Phase 10)

Reads receipt data FROM OneDrive Excel files, making Excel the single source of truth.

This module provides:
    - Reading receipt rows from Format① (Staff Ledger) and Format② (Location Ledger)
    - Converting Excel rows back to receipt objects
    - Listing all receipts currently in Excel
    - Finding specific receipts by criteria

Architecture (Phase 10):
    Excel (OneDrive) ←→ Excel Data Provider ←→ HQ API
                                           ←→ Sync Service
                                           ←→ Local DB

Author: Phase 10 - Excel as Single Source of Truth
Date: 2026-03-01
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.config.onedrive_structure import (
    get_location_file_path,
    get_staff_file_path,
    LOCATION_FOLDER,
    STAFF_FOLDER,
)
from app.services.excel_reader import (
    get_worksheet_names,
    read_worksheet,
    ExcelReadError,
    WorksheetNotFoundError,
)
from app.services.onedrive_file_manager import (
    list_files_in_folder,
    get_file_id,
    get_file_metadata,
    file_exists,
    OneDriveFileNotFoundError,
)
from app.services.graph_client import GraphAPIError

logger = logging.getLogger(__name__)


# =============================================================================
# COLUMN MAPPINGS (mirror of writer mappings for reading)
# =============================================================================

# Format① (Staff Ledger) column mapping
FORMAT1_COLUMNS = {
    0: "staff",           # A: 担当者
    1: "date",            # B: 支払日
    2: "account",         # C: 勘定科目
    3: "description",     # D: 摘要
    # 4: income (not used)
    5: "expense",         # F: 支出
    # 6: empty
    7: "invoice_flag",    # H: インボイス
    # 8-9: not used
    10: "tax_10",         # K: 10%税込額
    11: "tax_8",          # L: 8%税込額
}

FORMAT1_DATA_START_ROW = 2  # 0-indexed (Excel row 3)

# Format② (Location Ledger) column mapping
FORMAT2_COLUMNS = {
    0: "date",            # A: 支払日
    # 1: not used
    2: "description",     # C: 摘要/店舗
    3: "staff",           # D: 担当者
    # 4: not used
    5: "expense",         # F: 支出
    6: "invoice_flag",    # G: インボイス
    7: "account",         # H: 勘定科目
    # 8-9: not used
    10: "tax_10",         # K: 10%税込額
    11: "tax_8",          # L: 8%税込額
}

FORMAT2_DATA_START_ROW = 5  # 0-indexed (Excel row 6)

# Footer keywords to detect end of data
FOOTER_KEYWORDS = ["合計", "残高", "計"]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExcelReceiptRow:
    """
    Represents a single receipt row read from Excel.
    
    Contains all data from the Excel row plus metadata about its location.
    """
    # Excel location metadata
    file_id: str
    file_path: str
    worksheet_name: str
    row_index: int  # 0-indexed
    excel_row: int  # 1-indexed for display
    format_type: str  # "format1" or "format2"
    
    # Receipt data
    date: Optional[str] = None
    staff: Optional[str] = None
    description: Optional[str] = None
    account: Optional[str] = None
    expense: Optional[float] = None
    invoice_flag: Optional[str] = None
    tax_10: Optional[float] = None
    tax_8: Optional[float] = None
    
    # Additional metadata
    etag: Optional[str] = None
    location_id: Optional[str] = None
    last_read_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "excel_location": {
                "file_id": self.file_id,
                "file_path": self.file_path,
                "worksheet": self.worksheet_name,
                "row": self.excel_row,
                "format": self.format_type,
            },
            "receipt_data": {
                "date": self.date,
                "staff": self.staff,
                "description": self.description,
                "account": self.account,
                "expense": self.expense,
                "invoice_flag": self.invoice_flag,
                "tax_10": self.tax_10,
                "tax_8": self.tax_8,
            },
            "metadata": {
                "etag": self.etag,
                "location_id": self.location_id,
                "last_read_at": self.last_read_at.isoformat(),
            }
        }


@dataclass
class ExcelFileInfo:
    """Information about an Excel file on OneDrive."""
    file_id: str
    file_path: str
    file_name: str
    etag: str
    last_modified: Optional[datetime] = None
    row_count: int = 0
    worksheets: List[str] = field(default_factory=list)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _is_footer_row(row: List[Any]) -> bool:
    """Check if a row is a footer row (contains totals)."""
    for cell in row:
        if cell is not None:
            cell_str = str(cell).strip()
            for keyword in FOOTER_KEYWORDS:
                if keyword in cell_str:
                    return True
    return False


def _is_empty_row(row: List[Any], key_columns: List[int] = None) -> bool:
    """Check if a row is empty (no meaningful data)."""
    if key_columns:
        cells_to_check = [row[i] if i < len(row) else None for i in key_columns]
    else:
        cells_to_check = row
    
    return all(
        cell is None or (isinstance(cell, str) and cell.strip() == "")
        for cell in cells_to_check
    )


def _parse_excel_row(
    row: List[Any],
    column_mapping: Dict[int, str],
    row_index: int,
    file_id: str,
    file_path: str,
    worksheet_name: str,
    format_type: str,
    location_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> ExcelReceiptRow:
    """Parse an Excel row into an ExcelReceiptRow object."""
    
    def get_cell(col_idx: int) -> Any:
        return row[col_idx] if col_idx < len(row) else None
    
    # Extract values based on column mapping
    data = {}
    for col_idx, field_name in column_mapping.items():
        data[field_name] = get_cell(col_idx)
    
    return ExcelReceiptRow(
        file_id=file_id,
        file_path=file_path,
        worksheet_name=worksheet_name,
        row_index=row_index,
        excel_row=row_index + 1,
        format_type=format_type,
        date=data.get("date"),
        staff=data.get("staff"),
        description=data.get("description"),
        account=data.get("account"),
        expense=data.get("expense"),
        invoice_flag=data.get("invoice_flag"),
        tax_10=data.get("tax_10"),
        tax_8=data.get("tax_8"),
        location_id=location_id,
        etag=etag,
    )


# =============================================================================
# EXCEL DATA PROVIDER CLASS
# =============================================================================

class ExcelDataProvider:
    """
    Provides read access to receipt data stored in OneDrive Excel files.
    
    This is the core component of Phase 10 "Excel as Single Source of Truth".
    It reads data directly from Excel files via Graph API.
    
    Usage:
        provider = ExcelDataProvider()
        
        # List all receipts in a location's ledger
        receipts = provider.get_location_receipts("Aichi", 2026, 2)
        
        # Get a specific receipt by row
        receipt = provider.get_receipt_by_row(file_id, sheet_name, row_index)
        
        # List all Excel files
        files = provider.list_excel_files()
    """
    
    def __init__(self):
        """Initialize the Excel data provider."""
        self.logger = logging.getLogger(__name__)
    
    # =========================================================================
    # FILE LISTING
    # =========================================================================
    
    def list_location_files(self) -> List[ExcelFileInfo]:
        """
        List all Format② (location ledger) files in OneDrive.
        
        Returns:
            List of ExcelFileInfo for each location ledger file
        """
        files = []
        
        try:
            items = list_files_in_folder(LOCATION_FOLDER)
            
            for item in items:
                if not item.get("name", "").endswith(".xlsx"):
                    continue
                
                file_info = ExcelFileInfo(
                    file_id=item.get("id", ""),
                    file_path=f"{LOCATION_FOLDER}/{item.get('name', '')}",
                    file_name=item.get("name", ""),
                    etag=item.get("eTag", ""),
                    last_modified=self._parse_datetime(
                        item.get("lastModifiedDateTime")
                    ),
                )
                files.append(file_info)
            
            self.logger.info(f"Found {len(files)} location ledger files")
            return files
            
        except Exception as e:
            self.logger.error(f"Failed to list location files: {e}")
            return []
    
    def list_staff_files(self) -> List[ExcelFileInfo]:
        """
        List all Format① (staff ledger) files in OneDrive.
        
        Returns:
            List of ExcelFileInfo for each staff ledger file
        """
        files = []
        
        try:
            items = list_files_in_folder(STAFF_FOLDER)
            
            for item in items:
                if not item.get("name", "").endswith(".xlsx"):
                    continue
                
                file_info = ExcelFileInfo(
                    file_id=item.get("id", ""),
                    file_path=f"{STAFF_FOLDER}/{item.get('name', '')}",
                    file_name=item.get("name", ""),
                    etag=item.get("eTag", ""),
                    last_modified=self._parse_datetime(
                        item.get("lastModifiedDateTime")
                    ),
                )
                files.append(file_info)
            
            self.logger.info(f"Found {len(files)} staff ledger files")
            return files
            
        except Exception as e:
            self.logger.error(f"Failed to list staff files: {e}")
            return []
    
    # =========================================================================
    # READING RECEIPTS FROM FORMAT② (LOCATION LEDGER)
    # =========================================================================
    
    def get_location_receipts(
        self,
        location_id: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        worksheet_name: Optional[str] = None,
    ) -> List[ExcelReceiptRow]:
        """
        Read all receipt rows from a location's ledger file.
        
        Args:
            location_id: Business location identifier
            year: Optional year filter (uses worksheet naming)
            month: Optional month filter (uses worksheet naming)
            worksheet_name: Optional specific worksheet to read
            
        Returns:
            List of ExcelReceiptRow objects
        """
        file_path = get_location_file_path(location_id)
        
        try:
            file_id = get_file_id(file_path)
        except OneDriveFileNotFoundError:
            self.logger.warning(f"Location file not found: {file_path}")
            return []
        
        # Get file metadata for ETag
        try:
            metadata = get_file_metadata(file_id)
            etag = metadata.get("eTag")
        except Exception:
            etag = None
        
        # Determine which worksheets to read
        if worksheet_name:
            worksheets_to_read = [worksheet_name]
        elif year and month:
            # Format② uses YYYY年M月 naming
            worksheets_to_read = [f"{year}年{month}月"]
        else:
            # Read all worksheets
            try:
                worksheets_to_read = get_worksheet_names(file_id)
            except ExcelReadError:
                self.logger.error(f"Failed to get worksheets for {file_path}")
                return []
        
        receipts = []
        
        for ws_name in worksheets_to_read:
            ws_receipts = self._read_format2_worksheet(
                file_id=file_id,
                file_path=file_path,
                worksheet_name=ws_name,
                location_id=location_id,
                etag=etag,
            )
            receipts.extend(ws_receipts)
        
        self.logger.info(
            f"Read {len(receipts)} receipts from {location_id} "
            f"({len(worksheets_to_read)} worksheets)"
        )
        return receipts
    
    def _read_format2_worksheet(
        self,
        file_id: str,
        file_path: str,
        worksheet_name: str,
        location_id: str,
        etag: Optional[str] = None,
    ) -> List[ExcelReceiptRow]:
        """Read all receipt rows from a Format② worksheet."""
        try:
            rows = read_worksheet(file_id, worksheet_name)
        except WorksheetNotFoundError:
            self.logger.debug(f"Worksheet {worksheet_name} not found in {file_path}")
            return []
        except ExcelReadError as e:
            self.logger.error(f"Failed to read {worksheet_name}: {e}")
            return []
        
        receipts = []
        
        for row_idx, row in enumerate(rows):
            # Skip header rows
            if row_idx < FORMAT2_DATA_START_ROW:
                continue
            
            # Stop at footer
            if _is_footer_row(row):
                break
            
            # Skip empty rows
            if _is_empty_row(row, [0, 2, 3, 5]):  # Key columns for Format②
                continue
            
            receipt = _parse_excel_row(
                row=row,
                column_mapping=FORMAT2_COLUMNS,
                row_index=row_idx,
                file_id=file_id,
                file_path=file_path,
                worksheet_name=worksheet_name,
                format_type="format2",
                location_id=location_id,
                etag=etag,
            )
            receipts.append(receipt)
        
        return receipts
    
    # =========================================================================
    # READING RECEIPTS FROM FORMAT① (STAFF LEDGER)
    # =========================================================================
    
    def get_staff_receipts(
        self,
        staff_name: str,
        location_id: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        worksheet_name: Optional[str] = None,
    ) -> List[ExcelReceiptRow]:
        """
        Read all receipt rows from a staff member's ledger file.
        
        Args:
            staff_name: Staff member's display name
            location_id: Business location identifier
            year: Optional year filter
            month: Optional month filter
            worksheet_name: Optional specific worksheet to read
            
        Returns:
            List of ExcelReceiptRow objects
        """
        file_path = get_staff_file_path(staff_name, location_id)
        
        try:
            file_id = get_file_id(file_path)
        except OneDriveFileNotFoundError:
            self.logger.warning(f"Staff file not found: {file_path}")
            return []
        
        # Get file metadata for ETag
        try:
            metadata = get_file_metadata(file_id)
            etag = metadata.get("eTag")
        except Exception:
            etag = None
        
        # Determine which worksheets to read
        if worksheet_name:
            worksheets_to_read = [worksheet_name]
        elif year and month:
            # Format① uses YYYYMM naming
            worksheets_to_read = [f"{year}{month:02d}"]
        else:
            try:
                worksheets_to_read = get_worksheet_names(file_id)
            except ExcelReadError:
                return []
        
        receipts = []
        
        for ws_name in worksheets_to_read:
            ws_receipts = self._read_format1_worksheet(
                file_id=file_id,
                file_path=file_path,
                worksheet_name=ws_name,
                location_id=location_id,
                staff_name=staff_name,
                etag=etag,
            )
            receipts.extend(ws_receipts)
        
        return receipts
    
    def _read_format1_worksheet(
        self,
        file_id: str,
        file_path: str,
        worksheet_name: str,
        location_id: str,
        staff_name: str,
        etag: Optional[str] = None,
    ) -> List[ExcelReceiptRow]:
        """Read all receipt rows from a Format① worksheet."""
        try:
            rows = read_worksheet(file_id, worksheet_name)
        except WorksheetNotFoundError:
            return []
        except ExcelReadError as e:
            self.logger.error(f"Failed to read {worksheet_name}: {e}")
            return []
        
        receipts = []
        
        for row_idx, row in enumerate(rows):
            # Skip header rows
            if row_idx < FORMAT1_DATA_START_ROW:
                continue
            
            # Stop at footer
            if _is_footer_row(row):
                break
            
            # Skip empty rows
            if _is_empty_row(row, [0, 1, 3, 5]):  # Key columns for Format①
                continue
            
            receipt = _parse_excel_row(
                row=row,
                column_mapping=FORMAT1_COLUMNS,
                row_index=row_idx,
                file_id=file_id,
                file_path=file_path,
                worksheet_name=worksheet_name,
                format_type="format1",
                location_id=location_id,
                etag=etag,
            )
            receipts.append(receipt)
        
        return receipts
    
    # =========================================================================
    # SPECIFIC ROW ACCESS
    # =========================================================================
    
    def get_receipt_by_row(
        self,
        file_id: str,
        worksheet_name: str,
        row_index: int,
        format_type: str = "format2",
    ) -> Optional[ExcelReceiptRow]:
        """
        Get a specific receipt by its Excel row location.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Name of the worksheet
            row_index: 0-indexed row number
            format_type: "format1" or "format2"
            
        Returns:
            ExcelReceiptRow or None if not found
        """
        try:
            rows = read_worksheet(file_id, worksheet_name)
        except (WorksheetNotFoundError, ExcelReadError):
            return None
        
        if row_index >= len(rows):
            return None
        
        row = rows[row_index]
        
        # Get file metadata
        try:
            metadata = get_file_metadata(file_id)
            etag = metadata.get("eTag")
            file_path = metadata.get("name", "")
        except Exception:
            etag = None
            file_path = ""
        
        column_mapping = FORMAT1_COLUMNS if format_type == "format1" else FORMAT2_COLUMNS
        
        return _parse_excel_row(
            row=row,
            column_mapping=column_mapping,
            row_index=row_index,
            file_id=file_id,
            file_path=file_path,
            worksheet_name=worksheet_name,
            format_type=format_type,
            etag=etag,
        )
    
    # =========================================================================
    # AGGREGATE OPERATIONS
    # =========================================================================
    
    def get_all_location_receipts(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Dict[str, List[ExcelReceiptRow]]:
        """
        Get receipts from ALL location ledger files.
        
        Args:
            year: Optional year filter
            month: Optional month filter
            
        Returns:
            Dict mapping location_id to list of receipts
        """
        result = {}
        
        files = self.list_location_files()
        
        for file_info in files:
            # Extract location ID from filename
            # Filename format: {LOCATION}_Accumulated.xlsx
            filename = file_info.file_name
            if filename.endswith("_Accumulated.xlsx"):
                location_id = filename.replace("_Accumulated.xlsx", "")
            else:
                location_id = filename.replace(".xlsx", "")
            
            receipts = self.get_location_receipts(
                location_id=location_id,
                year=year,
                month=month,
            )
            
            if receipts:
                result[location_id] = receipts
        
        total_count = sum(len(r) for r in result.values())
        self.logger.info(
            f"Retrieved {total_count} receipts from {len(result)} locations"
        )
        return result
    
    def count_receipts_in_location(
        self,
        location_id: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> int:
        """Count receipts in a location's ledger without loading all data."""
        receipts = self.get_location_receipts(location_id, year, month)
        return len(receipts)
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_provider_instance: Optional[ExcelDataProvider] = None


def get_excel_data_provider() -> ExcelDataProvider:
    """Get or create the singleton ExcelDataProvider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = ExcelDataProvider()
    return _provider_instance
