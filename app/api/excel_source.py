"""
Excel Source API (Phase 10)

API endpoints that read directly from OneDrive Excel files.
These endpoints provide the "Excel as Single Source of Truth" view.

Endpoints:
    GET /api/excel/locations - List all location ledger files
    GET /api/excel/locations/{location_id}/receipts - Get receipts from location ledger
    GET /api/excel/staff - List all staff ledger files
    GET /api/excel/staff/{staff_name}/{location_id}/receipts - Get staff receipts
    GET /api/excel/sync-status - Get sync status for tracked files
    PUT /api/excel/row/{file_id}/{worksheet}/{row} - Update a specific row

Author: Phase 10 - Excel as Single Source of Truth
Updated: Phase 9 Step 1 - Safety stabilization (2026-03-20)
Date: 2026-03-01
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.excel_data_provider import (
    ExcelDataProvider,
    ExcelReceiptRow,
    ExcelFileInfo,
    get_excel_data_provider,
)
from app.services.excel_sync_service import (
    ExcelSyncService,
    SyncStatus,
    get_excel_sync_service,
)
from app.services.access_control_service import AccessControlService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/excel", tags=["excel-source"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ExcelFileResponse(BaseModel):
    """Excel file information."""
    file_id: str
    file_path: str
    file_name: str
    etag: str
    last_modified: Optional[str] = None
    row_count: int = 0


class ExcelReceiptResponse(BaseModel):
    """Receipt data from Excel."""
    excel_row: int
    row_index: int
    worksheet: str
    file_id: str
    format_type: str
    date: Optional[str] = None
    staff: Optional[str] = None
    description: Optional[str] = None
    account: Optional[str] = None
    expense: Optional[float] = None
    invoice_flag: Optional[str] = None
    tax_10: Optional[float] = None
    tax_8: Optional[float] = None
    etag: Optional[str] = None


class LocationReceiptsResponse(BaseModel):
    """Response for location receipts query."""
    location_id: str
    file_path: str
    worksheet_count: int
    receipt_count: int
    receipts: List[ExcelReceiptResponse]
    read_at: str


class RowUpdateRequest(BaseModel):
    """Request to update a row in Excel."""
    date: Optional[str] = None
    staff: Optional[str] = None
    description: Optional[str] = None
    account: Optional[str] = None
    expense: Optional[float] = None
    invoice_flag: Optional[str] = None
    tax_10: Optional[float] = None
    tax_8: Optional[float] = None
    etag: str = Field(..., description="Current ETag for concurrency check")


class RowUpdateResponse(BaseModel):
    """Response from row update."""
    success: bool
    row_index: int
    new_etag: Optional[str] = None
    error: Optional[str] = None


class SyncStatusResponse(BaseModel):
    """Sync status check response."""
    status: str
    message: str
    local_data: Optional[Dict[str, Any]] = None
    excel_data: Optional[Dict[str, Any]] = None
    conflicts: List[str] = []
    new_etag: Optional[str] = None


class AllLocationsResponse(BaseModel):
    """Response for all locations query."""
    location_count: int
    total_receipts: int
    locations: Dict[str, List[ExcelReceiptResponse]]
    read_at: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _ensure_hq_or_admin(current_user: User) -> None:
    """Ensure user has HQ or ADMIN role.
    
    Phase 12A-2: Delegates to AccessControlService for centralized logic.
    """
    if not AccessControlService.is_admin_or_hq(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. HQ or ADMIN role required.",
        )


def _require_graph_api_configured() -> None:
    """
    Phase 9 Step 1: Ensure Graph API is properly configured before any Excel operations.
    
    Raises HTTPException with 503 Service Unavailable if Graph API credentials
    are missing or placeholder values.
    
    This prevents unclear crashes when attempting OneDrive operations without credentials.
    """
    try:
        from app.services.graph_auth import is_graph_api_configured
        
        if not is_graph_api_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Graph API not configured. Excel Source API requires valid Microsoft 365 credentials. Phase 10 PoC required before this API is available.",
            )
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph API module not available.",
        )


def _receipt_row_to_response(row: ExcelReceiptRow) -> ExcelReceiptResponse:
    """Convert ExcelReceiptRow to API response model."""
    return ExcelReceiptResponse(
        excel_row=row.excel_row,
        row_index=row.row_index,
        worksheet=row.worksheet_name,
        file_id=row.file_id,
        format_type=row.format_type,
        date=str(row.date) if row.date else None,
        staff=str(row.staff) if row.staff else None,
        description=str(row.description) if row.description else None,
        account=str(row.account) if row.account else None,
        expense=float(row.expense) if row.expense else None,
        invoice_flag=str(row.invoice_flag) if row.invoice_flag else None,
        tax_10=float(row.tax_10) if row.tax_10 else None,
        tax_8=float(row.tax_8) if row.tax_8 else None,
        etag=row.etag,
    )


# =============================================================================
# FILE LISTING ENDPOINTS
# =============================================================================

@router.get("/locations", response_model=List[ExcelFileResponse])
async def list_location_files(
    current_user: User = Depends(get_current_user),
) -> List[ExcelFileResponse]:
    """
    List all Format② (location ledger) Excel files in OneDrive.
    
    Returns list of location ledger files with metadata.
    
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    provider = get_excel_data_provider()
    files = provider.list_location_files()
    
    return [
        ExcelFileResponse(
            file_id=f.file_id,
            file_path=f.file_path,
            file_name=f.file_name,
            etag=f.etag,
            last_modified=f.last_modified.isoformat() if f.last_modified else None,
            row_count=f.row_count,
        )
        for f in files
    ]


@router.get("/staff", response_model=List[ExcelFileResponse])
async def list_staff_files(
    current_user: User = Depends(get_current_user),
) -> List[ExcelFileResponse]:
    """
    List all Format① (staff ledger) Excel files in OneDrive.
    
    Returns list of staff ledger files with metadata.
    
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    provider = get_excel_data_provider()
    files = provider.list_staff_files()
    
    return [
        ExcelFileResponse(
            file_id=f.file_id,
            file_path=f.file_path,
            file_name=f.file_name,
            etag=f.etag,
            last_modified=f.last_modified.isoformat() if f.last_modified else None,
            row_count=f.row_count,
        )
        for f in files
    ]


# =============================================================================
# RECEIPT READING ENDPOINTS
# =============================================================================

@router.get("/locations/{location_id}/receipts", response_model=LocationReceiptsResponse)
async def get_location_receipts(
    location_id: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month"),
    worksheet: Optional[str] = Query(None, description="Specific worksheet name"),
    current_user: User = Depends(get_current_user),
) -> LocationReceiptsResponse:
    """
    Get all receipts from a location's Excel ledger.
    
    This reads directly from the OneDrive Excel file - the source of truth.
    
    Args:
        location_id: Business location identifier (e.g., "Aichi")
        year: Optional year filter
        month: Optional month filter (1-12)
        worksheet: Optional specific worksheet name
    
    Returns:
        All receipts from the location's ledger file
        
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    provider = get_excel_data_provider()
    
    try:
        receipts = provider.get_location_receipts(
            location_id=location_id,
            year=year,
            month=month,
            worksheet_name=worksheet,
        )
    except Exception as e:
        logger.error(f"Failed to read location receipts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read Excel file: {str(e)}",
        )
    
    # Get unique worksheets
    worksheets = set(r.worksheet_name for r in receipts)
    
    # Get file path from first receipt or construct it
    file_path = receipts[0].file_path if receipts else f"locations/{location_id}_Accumulated.xlsx"
    
    return LocationReceiptsResponse(
        location_id=location_id,
        file_path=file_path,
        worksheet_count=len(worksheets),
        receipt_count=len(receipts),
        receipts=[_receipt_row_to_response(r) for r in receipts],
        read_at=datetime.utcnow().isoformat(),
    )


@router.get("/staff/{staff_name}/{location_id}/receipts")
async def get_staff_receipts(
    staff_name: str,
    location_id: str,
    year: Optional[int] = Query(None, description="Filter by year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get all receipts from a staff member's Excel ledger.
    
    Args:
        staff_name: Staff member's display name
        location_id: Business location identifier
        year: Optional year filter
        month: Optional month filter
    
    Returns:
        All receipts from the staff's ledger file
        
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    provider = get_excel_data_provider()
    
    try:
        receipts = provider.get_staff_receipts(
            staff_name=staff_name,
            location_id=location_id,
            year=year,
            month=month,
        )
    except Exception as e:
        logger.error(f"Failed to read staff receipts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read Excel file: {str(e)}",
        )
    
    return {
        "staff_name": staff_name,
        "location_id": location_id,
        "receipt_count": len(receipts),
        "receipts": [_receipt_row_to_response(r) for r in receipts],
        "read_at": datetime.utcnow().isoformat(),
    }


@router.get("/all-locations", response_model=AllLocationsResponse)
async def get_all_location_receipts(
    year: Optional[int] = Query(None, description="Filter by year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month"),
    current_user: User = Depends(get_current_user),
) -> AllLocationsResponse:
    """
    Get receipts from ALL location ledger files.
    
    This is useful for HQ overview - see all data across all locations.
    
    Args:
        year: Optional year filter
        month: Optional month filter
    
    Returns:
        All receipts grouped by location
        
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    provider = get_excel_data_provider()
    
    try:
        all_receipts = provider.get_all_location_receipts(year=year, month=month)
    except Exception as e:
        logger.error(f"Failed to read all location receipts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read Excel files: {str(e)}",
        )
    
    # Convert to response format
    locations_data = {
        loc_id: [_receipt_row_to_response(r) for r in receipts]
        for loc_id, receipts in all_receipts.items()
    }
    
    total = sum(len(r) for r in all_receipts.values())
    
    return AllLocationsResponse(
        location_count=len(all_receipts),
        total_receipts=total,
        locations=locations_data,
        read_at=datetime.utcnow().isoformat(),
    )


# =============================================================================
# ROW UPDATE ENDPOINTS
# =============================================================================

@router.put("/row/{file_id}/{worksheet}/{row_index}", response_model=RowUpdateResponse)
async def update_excel_row(
    file_id: str,
    worksheet: str,
    row_index: int,
    update_data: RowUpdateRequest,
    format_type: str = Query("format2", description="format1 or format2"),
    current_user: User = Depends(get_current_user),
) -> RowUpdateResponse:
    """
    Update a specific row in an Excel file.
    
    Uses ETag-based optimistic locking to prevent concurrent modifications.
    
    Args:
        file_id: OneDrive file ID
        worksheet: Worksheet name
        row_index: 0-indexed row number
        update_data: Fields to update
        format_type: "format1" or "format2"
    
    Returns:
        Success status and new ETag
        
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    sync_service = get_excel_sync_service()
    
    # Build update data dict
    data = {
        k: v for k, v in {
            "date": update_data.date,
            "staff": update_data.staff,
            "description": update_data.description,
            "account": update_data.account,
            "expense": update_data.expense,
            "invoice_flag": update_data.invoice_flag,
            "tax_10": update_data.tax_10,
            "tax_8": update_data.tax_8,
        }.items() if v is not None
    }
    
    result = sync_service.update_excel_row(
        file_id=file_id,
        worksheet_name=worksheet,
        row_index=row_index,
        data=data,
        etag=update_data.etag,
        format_type=format_type,
    )
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if "Concurrent" in (result.error or "") 
                else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error,
        )
    
    return RowUpdateResponse(
        success=result.success,
        row_index=result.row_index,
        new_etag=result.new_etag,
        error=result.error,
    )


@router.put("/row/{file_id}/{worksheet}/{row_index}/retry", response_model=RowUpdateResponse)
async def update_excel_row_with_retry(
    file_id: str,
    worksheet: str,
    row_index: int,
    update_data: RowUpdateRequest,
    format_type: str = Query("format2", description="format1 or format2"),
    max_retries: int = Query(3, ge=1, le=10, description="Max retry attempts"),
    current_user: User = Depends(get_current_user),
) -> RowUpdateResponse:
    """
    Update a row with automatic ETag refresh and retry on conflict.
    
    This endpoint automatically handles concurrent modification conflicts
    by refreshing the ETag and retrying.
    
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    sync_service = get_excel_sync_service()
    
    data = {
        k: v for k, v in {
            "date": update_data.date,
            "staff": update_data.staff,
            "description": update_data.description,
            "account": update_data.account,
            "expense": update_data.expense,
            "invoice_flag": update_data.invoice_flag,
            "tax_10": update_data.tax_10,
            "tax_8": update_data.tax_8,
        }.items() if v is not None
    }
    
    result = sync_service.update_excel_row_with_retry(
        file_id=file_id,
        worksheet_name=worksheet,
        row_index=row_index,
        data=data,
        format_type=format_type,
        max_retries=max_retries,
    )
    
    return RowUpdateResponse(
        success=result.success,
        row_index=result.row_index,
        new_etag=result.new_etag,
        error=result.error,
    )


# =============================================================================
# SYNC STATUS ENDPOINTS
# =============================================================================

@router.get("/sync-status/{file_id}")
async def check_file_sync_status(
    file_id: str,
    known_etag: Optional[str] = Query(None, description="Last known ETag"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Check if a file has been modified since the known ETag.
    
    Useful for detecting external modifications before updating.
    
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    _ensure_hq_or_admin(current_user)
    
    from app.services.onedrive_file_manager import get_file_metadata
    
    try:
        metadata = get_file_metadata(file_id)
        current_etag = metadata.get("eTag")
        
        modified = known_etag is not None and current_etag != known_etag
        
        return {
            "file_id": file_id,
            "current_etag": current_etag,
            "known_etag": known_etag,
            "modified": modified,
            "last_modified": metadata.get("lastModifiedDateTime"),
            "modified_by": metadata.get("lastModifiedBy", {}).get("user", {}).get("displayName"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get file metadata: {str(e)}",
        )


# =============================================================================
# DASHBOARD ENDPOINT
# =============================================================================

@router.get("/dashboard")
async def excel_dashboard() -> Dict[str, Any]:
    """
    Get Phase 10 dashboard with summary statistics.
    
    Returns overview of Excel data without authentication (for demo).
    
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    provider = get_excel_data_provider()
    
    try:
        location_files = provider.list_location_files()
        staff_files = provider.list_staff_files()
        
        # Calculate totals
        total_location_rows = sum(f.row_count or 0 for f in location_files)
        total_staff_rows = sum(f.row_count or 0 for f in staff_files)
        
        # Get most recent modification
        latest_mod = None
        for f in location_files + staff_files:
            if f.last_modified and (latest_mod is None or f.last_modified > latest_mod):
                latest_mod = f.last_modified
        
        return {
            "status": "connected",
            "summary": {
                "location_files": len(location_files),
                "staff_files": len(staff_files),
                "total_location_rows": total_location_rows,
                "total_staff_rows": total_staff_rows,
                "total_rows": total_location_rows + total_staff_rows,
            },
            "locations": [
                {
                    "name": f.file_name.replace("_Accumulated.xlsx", ""),
                    "file_id": f.file_id,
                    "rows": f.row_count or 0,
                    "last_modified": f.last_modified.isoformat() if f.last_modified else None,
                }
                for f in location_files
            ],
            "latest_modification": latest_mod.isoformat() if latest_mod else None,
            "timestamp": datetime.utcnow().isoformat(),
            "phase": "Phase 10 - Excel as Source of Truth",
        }
    except Exception as e:
        return {
            "status": "disconnected",
            "error": str(e),
            "summary": {
                "location_files": 0,
                "staff_files": 0,
                "total_rows": 0,
            },
            "locations": [],
            "timestamp": datetime.utcnow().isoformat(),
            "phase": "Phase 10 - Excel as Source of Truth",
            "hint": "OneDrive may not be configured or 'locations' folder may not exist yet",
        }


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def excel_api_health() -> Dict[str, Any]:
    """
    Check health of the Excel Source API.
    
    Verifies connectivity to OneDrive and Graph API.
    
    Note: Requires Graph API to be configured (Phase 10 PoC).
    """
    _require_graph_api_configured()
    provider = get_excel_data_provider()
    
    try:
        # Try to list location files as a health check
        files = provider.list_location_files()
        
        return {
            "status": "healthy",
            "service": "Excel Source API (Phase 10)",
            "timestamp": datetime.utcnow().isoformat(),
            "location_files_count": len(files),
            "message": "Excel Source API is operational",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "message": "Failed to connect to OneDrive",
        }
