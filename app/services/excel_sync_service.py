"""
Excel Sync Service (Phase 10)

Bidirectional synchronization between local database and OneDrive Excel files.

This module provides:
    - Sync status tracking between local DB and Excel
    - Detection of external Excel modifications
    - Writeback of local changes to Excel rows
    - Conflict resolution for concurrent edits

Architecture:
    Local DB (drafts) ←→ Excel Sync Service ←→ OneDrive Excel
                       ↓
                   Audit Log

Author: Phase 10 - Excel as Single Source of Truth
Date: 2026-03-01
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.config.onedrive_structure import (
    get_location_file_path,
    get_staff_file_path,
)
from app.services.excel_data_provider import (
    ExcelDataProvider,
    ExcelReceiptRow,
    FORMAT2_COLUMNS,
    FORMAT1_COLUMNS,
    FORMAT2_DATA_START_ROW,
    FORMAT1_DATA_START_ROW,
    get_excel_data_provider,
)
from app.services.excel_writer import (
    update_range,
    ETagConflictError,
    ExcelWriteError,
)
from app.services.onedrive_file_manager import (
    get_file_id,
    get_file_metadata,
    OneDriveFileNotFoundError,
)
from app.services.conflict_resolver import (
    safe_write,
    WriteConflictError,
)
from app.constants.status_workflow import (
    ReceiptStatus,
    is_finalized,
    requires_audit_for_edit,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class SyncStatus(str, Enum):
    """Synchronization status between local and Excel."""
    SYNCED = "synced"              # Local and Excel match
    LOCAL_MODIFIED = "local_modified"  # Local has unsent changes
    EXCEL_MODIFIED = "excel_modified"  # Excel was modified externally
    CONFLICT = "conflict"          # Both modified - needs resolution
    NOT_IN_EXCEL = "not_in_excel"  # Local only, not yet sent
    EXCEL_ONLY = "excel_only"      # Excel only, not in local DB


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    status: SyncStatus
    message: str
    local_data: Optional[Dict[str, Any]] = None
    excel_data: Optional[Dict[str, Any]] = None
    conflicts: List[str] = field(default_factory=list)
    new_etag: Optional[str] = None


@dataclass
class ExcelRowLocation:
    """Location of a receipt row in Excel."""
    file_id: str
    file_path: str
    worksheet_name: str
    row_index: int  # 0-indexed
    etag: str
    format_type: str  # "format1" or "format2"


@dataclass
class RowUpdateResult:
    """Result of updating a single row in Excel."""
    success: bool
    row_index: int
    new_etag: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# COLUMN TO VALUE MAPPING
# =============================================================================

def _build_format2_row_values(data: Dict[str, Any], num_cols: int = 14) -> List[Any]:
    """
    Build a row values array for Format② from a data dictionary.
    
    Args:
        data: Dictionary with keys like 'date', 'description', 'staff', etc.
        num_cols: Number of columns in the row
        
    Returns:
        List of cell values
    """
    row = [None] * num_cols
    
    # Reverse mapping: field name -> column index
    field_to_col = {v: k for k, v in FORMAT2_COLUMNS.items()}
    
    for field_name, value in data.items():
        if field_name in field_to_col:
            col_idx = field_to_col[field_name]
            if col_idx < num_cols:
                row[col_idx] = value
    
    return row


def _build_format1_row_values(data: Dict[str, Any], num_cols: int = 14) -> List[Any]:
    """
    Build a row values array for Format① from a data dictionary.
    
    Args:
        data: Dictionary with keys like 'date', 'description', 'staff', etc.
        num_cols: Number of columns in the row
        
    Returns:
        List of cell values
    """
    row = [None] * num_cols
    
    # Reverse mapping: field name -> column index
    field_to_col = {v: k for k, v in FORMAT1_COLUMNS.items()}
    
    for field_name, value in data.items():
        if field_name in field_to_col:
            col_idx = field_to_col[field_name]
            if col_idx < num_cols:
                row[col_idx] = value
    
    return row


def _column_letter(index: int) -> str:
    """Convert 0-indexed column number to Excel letter."""
    result = ""
    while index >= 0:
        result = chr(index % 26 + ord('A')) + result
        index = index // 26 - 1
    return result


# =============================================================================
# EXCEL SYNC SERVICE
# =============================================================================

class ExcelSyncService:
    """
    Service for synchronizing data between local database and OneDrive Excel.
    
    This is the core synchronization component of Phase 10.
    It handles:
        - Checking sync status
        - Updating existing Excel rows
        - Detecting external modifications
        - Resolving conflicts
    
    Usage:
        sync = ExcelSyncService()
        
        # Check sync status
        status = sync.check_sync_status(draft)
        
        # Update a row in Excel
        result = sync.update_excel_row(
            file_id=draft.format2_file_id,
            worksheet="2026年3月",
            row_index=draft.format2_row_index,
            data={'expense': 1500, 'description': 'Updated'},
            etag=draft.format2_etag,
            format_type="format2"
        )
    """
    
    def __init__(
        self,
        data_provider: Optional[ExcelDataProvider] = None,
    ):
        """Initialize the sync service."""
        self._data_provider = data_provider or get_excel_data_provider()
        self.logger = logging.getLogger(__name__)
    
    # =========================================================================
    # SYNC STATUS CHECKING
    # =========================================================================
    
    def check_sync_status(
        self,
        local_data: Dict[str, Any],
        excel_location: ExcelRowLocation,
    ) -> SyncResult:
        """
        Check synchronization status between local data and Excel.
        
        Args:
            local_data: Local receipt data dictionary
            excel_location: Location of the Excel row
            
        Returns:
            SyncResult indicating current status
        """
        # Read current Excel state
        excel_row = self._data_provider.get_receipt_by_row(
            file_id=excel_location.file_id,
            worksheet_name=excel_location.worksheet_name,
            row_index=excel_location.row_index,
            format_type=excel_location.format_type,
        )
        
        if excel_row is None:
            return SyncResult(
                success=True,
                status=SyncStatus.NOT_IN_EXCEL,
                message="Row not found in Excel",
                local_data=local_data,
            )
        
        # Check if ETag has changed
        try:
            current_meta = get_file_metadata(excel_location.file_id)
            current_etag = current_meta.get("eTag")
        except Exception:
            current_etag = None
        
        etag_changed = current_etag and current_etag != excel_location.etag
        
        # Compare data
        conflicts = self._compare_data(local_data, excel_row.to_dict()["receipt_data"])
        
        if not conflicts and not etag_changed:
            return SyncResult(
                success=True,
                status=SyncStatus.SYNCED,
                message="Local and Excel are in sync",
                local_data=local_data,
                excel_data=excel_row.to_dict(),
                new_etag=current_etag,
            )
        
        if etag_changed and conflicts:
            return SyncResult(
                success=True,
                status=SyncStatus.CONFLICT,
                message="Both local and Excel have been modified",
                local_data=local_data,
                excel_data=excel_row.to_dict(),
                conflicts=conflicts,
                new_etag=current_etag,
            )
        
        if etag_changed:
            return SyncResult(
                success=True,
                status=SyncStatus.EXCEL_MODIFIED,
                message="Excel was modified externally",
                local_data=local_data,
                excel_data=excel_row.to_dict(),
                new_etag=current_etag,
            )
        
        return SyncResult(
            success=True,
            status=SyncStatus.LOCAL_MODIFIED,
            message="Local has unsent changes",
            local_data=local_data,
            excel_data=excel_row.to_dict(),
            conflicts=conflicts,
        )
    
    def _compare_data(
        self,
        local: Dict[str, Any],
        excel: Dict[str, Any],
    ) -> List[str]:
        """
        Compare local and Excel data, return list of differing fields.
        """
        conflicts = []
        
        # Fields to compare
        compare_fields = ["date", "description", "staff", "account", 
                         "expense", "invoice_flag", "tax_10", "tax_8"]
        
        for field in compare_fields:
            local_val = local.get(field)
            excel_val = excel.get(field)
            
            # Normalize for comparison
            if local_val is None and excel_val == "":
                continue
            if excel_val is None and local_val == "":
                continue
            
            # Compare (with type coercion for numbers)
            try:
                if float(local_val or 0) != float(excel_val or 0):
                    conflicts.append(field)
            except (ValueError, TypeError):
                if str(local_val or "") != str(excel_val or ""):
                    conflicts.append(field)
        
        return conflicts
    
    # =========================================================================
    # EXCEL ROW UPDATES
    # =========================================================================
    
    def update_excel_row(
        self,
        file_id: str,
        worksheet_name: str,
        row_index: int,
        data: Dict[str, Any],
        etag: str,
        format_type: str = "format2",
        num_cols: int = 14,
    ) -> RowUpdateResult:
        """
        Update a single row in an Excel file.
        
        Uses ETag-based optimistic locking to prevent concurrent modification.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Name of the worksheet
            row_index: 0-indexed row number
            data: Dictionary of field values to update
            etag: Current ETag for concurrency check
            format_type: "format1" or "format2"
            num_cols: Number of columns in the row
            
        Returns:
            RowUpdateResult with success status and new ETag
        """
        # Build row values
        if format_type == "format1":
            row_values = _build_format1_row_values(data, num_cols)
        else:
            row_values = _build_format2_row_values(data, num_cols)
        
        # Build range address (e.g., "A7:N7" for row 7)
        excel_row = row_index + 1  # Convert to 1-indexed
        start_col = _column_letter(0)
        end_col = _column_letter(num_cols - 1)
        range_address = f"{start_col}{excel_row}:{end_col}{excel_row}"
        
        try:
            # Use safe_write from conflict_resolver for retry logic
            async def write_row():
                return update_range(
                    file_id=file_id,
                    worksheet_name=worksheet_name,
                    range_address=range_address,
                    values=[row_values],
                    etag=etag,
                )
            
            # For synchronous usage, call directly
            new_etag = update_range(
                file_id=file_id,
                worksheet_name=worksheet_name,
                range_address=range_address,
                values=[row_values],
                etag=etag,
            )
            
            self.logger.info(
                f"Updated Excel row {excel_row} in {worksheet_name}"
            )
            
            return RowUpdateResult(
                success=True,
                row_index=row_index,
                new_etag=new_etag,
            )
            
        except ETagConflictError as e:
            self.logger.warning(
                f"ETag conflict updating row {excel_row}: {e}"
            )
            return RowUpdateResult(
                success=False,
                row_index=row_index,
                error=f"Concurrent modification detected: {e}",
            )
            
        except ExcelWriteError as e:
            self.logger.error(f"Excel write error: {e}")
            return RowUpdateResult(
                success=False,
                row_index=row_index,
                error=str(e),
            )
            
        except Exception as e:
            self.logger.exception(f"Unexpected error updating row: {e}")
            return RowUpdateResult(
                success=False,
                row_index=row_index,
                error=str(e),
            )
    
    def update_excel_row_with_retry(
        self,
        file_id: str,
        worksheet_name: str,
        row_index: int,
        data: Dict[str, Any],
        format_type: str = "format2",
        max_retries: int = 3,
    ) -> RowUpdateResult:
        """
        Update a row with automatic ETag refresh and retry on conflict.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Name of the worksheet
            row_index: 0-indexed row number
            data: Dictionary of field values to update
            format_type: "format1" or "format2"
            max_retries: Maximum number of retry attempts
            
        Returns:
            RowUpdateResult with success status and new ETag
        """
        for attempt in range(max_retries):
            # Get current ETag
            try:
                metadata = get_file_metadata(file_id)
                current_etag = metadata.get("eTag")
            except Exception as e:
                return RowUpdateResult(
                    success=False,
                    row_index=row_index,
                    error=f"Failed to get file metadata: {e}",
                )
            
            result = self.update_excel_row(
                file_id=file_id,
                worksheet_name=worksheet_name,
                row_index=row_index,
                data=data,
                etag=current_etag,
                format_type=format_type,
            )
            
            if result.success:
                return result
            
            # Check if it's a retryable error
            if "Concurrent modification" not in (result.error or ""):
                return result
            
            self.logger.info(
                f"Retry {attempt + 1}/{max_retries} for row {row_index}"
            )
        
        return RowUpdateResult(
            success=False,
            row_index=row_index,
            error=f"Failed after {max_retries} retries",
        )
    
    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    
    def sync_location_to_excel(
        self,
        location_id: str,
        drafts: List[Dict[str, Any]],
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        Sync multiple drafts to a location's Excel ledger.
        
        Args:
            location_id: Business location identifier
            drafts: List of draft data dictionaries
            year: Target year
            month: Target month
            
        Returns:
            Summary of sync results
        """
        file_path = get_location_file_path(location_id)
        
        try:
            file_id = get_file_id(file_path)
        except OneDriveFileNotFoundError:
            return {
                "success": False,
                "error": f"Location file not found: {file_path}",
                "synced": 0,
                "failed": len(drafts),
            }
        
        worksheet_name = f"{year}年{month}月"
        
        results = {
            "success": True,
            "synced": 0,
            "failed": 0,
            "details": [],
        }
        
        for draft in drafts:
            row_index = draft.get("format2_row_index")
            etag = draft.get("format2_etag")
            
            if row_index is None:
                # New draft - would need to append, not update
                results["details"].append({
                    "draft_id": draft.get("id"),
                    "status": "skipped",
                    "reason": "No row index - needs append",
                })
                continue
            
            result = self.update_excel_row(
                file_id=file_id,
                worksheet_name=worksheet_name,
                row_index=row_index,
                data={
                    "date": draft.get("receipt_date"),
                    "description": draft.get("memo") or draft.get("vendor_name"),
                    "staff": draft.get("staff_name"),
                    "account": draft.get("account_title"),
                    "expense": draft.get("total_amount"),
                    "invoice_flag": "有" if draft.get("invoice_number") else "無",
                    "tax_10": draft.get("tax_10_amount"),
                    "tax_8": draft.get("tax_8_amount"),
                },
                etag=etag,
                format_type="format2",
            )
            
            if result.success:
                results["synced"] += 1
            else:
                results["failed"] += 1
                results["success"] = False
            
            results["details"].append({
                "draft_id": draft.get("id"),
                "row_index": row_index,
                "status": "success" if result.success else "failed",
                "error": result.error,
                "new_etag": result.new_etag,
            })
        
        return results
    
    # =========================================================================
    # EXTERNAL MODIFICATION DETECTION
    # =========================================================================
    
    def detect_external_changes(
        self,
        tracked_files: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Detect which tracked files have been modified externally.
        
        Args:
            tracked_files: List of dicts with 'file_id' and 'last_known_etag'
            
        Returns:
            List of files that have been modified
        """
        modified = []
        
        for tracked in tracked_files:
            file_id = tracked.get("file_id")
            last_etag = tracked.get("last_known_etag")
            
            if not file_id:
                continue
            
            try:
                metadata = get_file_metadata(file_id)
                current_etag = metadata.get("eTag")
                
                if current_etag != last_etag:
                    modified.append({
                        "file_id": file_id,
                        "old_etag": last_etag,
                        "new_etag": current_etag,
                        "last_modified": metadata.get("lastModifiedDateTime"),
                        "modified_by": metadata.get("lastModifiedBy", {}).get(
                            "user", {}
                        ).get("displayName"),
                    })
            except Exception as e:
                self.logger.warning(f"Failed to check file {file_id}: {e}")
        
        return modified


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_sync_service_instance: Optional[ExcelSyncService] = None


def get_excel_sync_service() -> ExcelSyncService:
    """Get or create the singleton ExcelSyncService instance."""
    global _sync_service_instance
    if _sync_service_instance is None:
        _sync_service_instance = ExcelSyncService()
    return _sync_service_instance
