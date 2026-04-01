"""Phase 13: Office→HQ transfer endpoints with Excel writes.

Provides endpoints for month-end transfer of SENT receipts to HQ Master Ledger.
Uses Graph API for Excel operations with ETag-based concurrency control.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.repositories.hq_transfer_repository import HQTransferRepository
from app.services.hq_transfer_service import HQTransferService, compute_reporting_month
from app.services.hq_transfer_writer_service import HQTransferWriterService
from app.utils.feature_flags import is_hq_transfer_enabled
from app.services.access_control_service import AccessControlService


logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/hq-transfer", tags=["hq-transfer"])

_hq_transfer_service: Optional[HQTransferService] = None
_hq_transfer_repository: Optional[HQTransferRepository] = None
_hq_transfer_writer_service: Optional[HQTransferWriterService] = None


def get_hq_transfer_service() -> HQTransferService:
    global _hq_transfer_service
    if _hq_transfer_service is None:
        _hq_transfer_service = HQTransferService()
    return _hq_transfer_service


def get_hq_transfer_repository() -> HQTransferRepository:
    global _hq_transfer_repository
    if _hq_transfer_repository is None:
        _hq_transfer_repository = HQTransferRepository()
    return _hq_transfer_repository


def get_hq_transfer_writer_service() -> HQTransferWriterService:
    """Get or create HQ Transfer Writer Service singleton (Phase 13)."""
    global _hq_transfer_writer_service
    if _hq_transfer_writer_service is None:
        _hq_transfer_writer_service = HQTransferWriterService()
    return _hq_transfer_writer_service


def _ensure_feature_enabled() -> None:
    if not is_hq_transfer_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _ensure_admin_only(current_user: User) -> None:
    """Ensure user has ADMIN role.
    
    Phase 12A-2: Delegates to AccessControlService for centralized logic.
    """
    if not AccessControlService.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. ADMIN role required.",
        )


class BeginHQTransferRequest(BaseModel):
    business_location_id: str = Field(..., min_length=1)
    submitted_at: Optional[datetime] = Field(default=None)


class BeginHQTransferResponse(BaseModel):
    batch_id: str
    reporting_month: str
    receipt_count: int


class PreviewHQTransferResponse(BaseModel):
    reporting_month: str
    candidate_count: int


@router.post("/begin", response_model=BeginHQTransferResponse)
def begin_hq_transfer(
    request: BeginHQTransferRequest,
    current_user: User = Depends(get_current_user),
):
    _ensure_feature_enabled()
    _ensure_admin_only(current_user)

    submitted_at = request.submitted_at or datetime.now(timezone.utc)
    reporting_month = compute_reporting_month(submitted_at)

    service = get_hq_transfer_service()
    repository = get_hq_transfer_repository()

    batch_id = service.begin_hq_transfer(
        location_id=request.business_location_id,
        submitted_at=submitted_at,
        user=current_user,
    )

    batch = repository.get_batch_by_id(batch_id)
    receipt_count = int((batch or {}).get("receipt_count", 0))

    logger.info(
        "hq_transfer_begin user_id=%s role=%s location_id=%s reporting_month=%s receipt_count=%s batch_id=%s",
        getattr(current_user, "user_id", None),
        getattr(current_user, "role", None),
        request.business_location_id,
        reporting_month,
        receipt_count,
        batch_id,
    )

    return BeginHQTransferResponse(
        batch_id=batch_id,
        reporting_month=reporting_month,
        receipt_count=receipt_count,
    )


@router.get("/preview", response_model=PreviewHQTransferResponse)
def preview_hq_transfer(
    business_location_id: str,
    current_user: User = Depends(get_current_user),
):
    _ensure_feature_enabled()
    _ensure_admin_only(current_user)

    submitted_at = datetime.now(timezone.utc)
    reporting_month = compute_reporting_month(submitted_at)

    service = get_hq_transfer_service()
    candidates = service.get_transfer_candidates(business_location_id, reporting_month)

    return PreviewHQTransferResponse(
        reporting_month=reporting_month,
        candidate_count=len(candidates),
    )


# =============================================================================
# PHASE 13: Month-End HQ Transfer with Excel Writes
# =============================================================================

class MonthEndTransferRequest(BaseModel):
    """Request payload for month-end HQ transfer."""
    office_id: str = Field(..., min_length=1, description="Business location/office ID")
    year: int = Field(..., ge=2020, le=2100, description="Transfer year")
    month: int = Field(..., ge=1, le=12, description="Transfer month (1-12)")


class MonthEndTransferError(BaseModel):
    """Individual error detail in transfer result."""
    draft_id: str
    error: str


class MonthEndTransferResponse(BaseModel):
    """Response for month-end HQ transfer operation."""
    batch_id: Optional[str] = None
    status: str  # "success", "partial_failure", "failed", "idempotent", "no_candidates"
    receipt_count: int
    written_count: Optional[int] = None
    failed_count: Optional[int] = None
    errors: Optional[List[MonthEndTransferError]] = None
    reporting_month: str
    message: Optional[str] = None


class TransferStatusResponse(BaseModel):
    """Response for transfer status query."""
    batch_id: Optional[str] = None
    office_id: str
    reporting_month: str
    status: Optional[str] = None  # "CREATED", "WRITING", "SUCCESS", "FAILED"
    created_at: Optional[str] = None
    receipt_count: Optional[int] = None
    error_message: Optional[str] = None


class PendingOffice(BaseModel):
    """Office with pending receipts for HQ transfer."""
    office_id: str
    pending_count: int


class PendingOfficesResponse(BaseModel):
    """Response for pending offices query."""
    reporting_month: str
    offices: List[PendingOffice]


@router.post("/month-end/execute", response_model=MonthEndTransferResponse)
def execute_month_end_transfer(
    request: MonthEndTransferRequest,
    current_user: User = Depends(get_current_user),
):
    """Execute month-end HQ transfer with Excel writes (Phase 13).
    
    This endpoint writes SENT receipts for the specified office-month
    to the HQ Master Ledger on OneDrive via Graph API.
    
    Features:
    - Idempotent: Returns existing batch if already transferred
    - Atomic: Uses ETag-based optimistic locking for concurrent safety
    - Audited: Every row write is logged to audit trail
    
    Requires ADMIN role.
    """
    _ensure_feature_enabled()
    _ensure_admin_only(current_user)
    
    user_id = str(getattr(current_user, "user_id", "system"))
    
    writer_service = get_hq_transfer_writer_service()
    result = writer_service.execute_month_end_transfer(
        office_id=request.office_id,
        year=request.year,
        month=request.month,
        user_id=user_id,
    )
    
    logger.info(
        "hq_month_end_transfer user_id=%s office_id=%s year=%d month=%d status=%s "
        "receipt_count=%d written=%s failed=%s batch_id=%s",
        user_id,
        request.office_id,
        request.year,
        request.month,
        result.get("status"),
        result.get("receipt_count", 0),
        result.get("written_count"),
        result.get("failed_count"),
        result.get("batch_id"),
    )
    
    # Convert errors list to response model format
    errors = None
    if result.get("errors"):
        errors = [
            MonthEndTransferError(draft_id=e["draft_id"], error=e["error"])
            for e in result["errors"]
        ]
    
    return MonthEndTransferResponse(
        batch_id=result.get("batch_id"),
        status=result["status"],
        receipt_count=result.get("receipt_count", 0),
        written_count=result.get("written_count"),
        failed_count=result.get("failed_count"),
        errors=errors,
        reporting_month=result["reporting_month"],
        message=result.get("message"),
    )


@router.get("/month-end/status", response_model=TransferStatusResponse)
def get_month_end_status(
    office_id: str,
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
):
    """Get HQ transfer status for an office-month (Phase 13).
    
    Returns the latest batch status for the specified office and month.
    """
    _ensure_feature_enabled()
    _ensure_admin_only(current_user)
    
    reporting_month = f"{year:04d}-{month:02d}"
    writer_service = get_hq_transfer_writer_service()
    
    batch = writer_service.get_transfer_status(office_id, reporting_month)
    
    if not batch:
        return TransferStatusResponse(
            office_id=office_id,
            reporting_month=reporting_month,
        )
    
    return TransferStatusResponse(
        batch_id=batch.get("batch_id"),
        office_id=office_id,
        reporting_month=reporting_month,
        status=batch.get("status"),
        created_at=batch.get("created_at"),
        receipt_count=batch.get("receipt_count"),
        error_message=batch.get("error_message"),
    )


@router.get("/month-end/preview")
def preview_month_end_transfer(
    office_id: str,
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
):
    """Preview SENT receipts available for HQ transfer (Phase 13).
    
    Returns count and summary of receipts that would be transferred.
    """
    _ensure_feature_enabled()
    _ensure_admin_only(current_user)
    
    reporting_month = f"{year:04d}-{month:02d}"
    writer_service = get_hq_transfer_writer_service()
    
    candidates = writer_service.get_transfer_candidates(office_id, reporting_month)
    
    # Check existing batch
    existing = writer_service.get_transfer_status(office_id, reporting_month)
    
    return {
        "office_id": office_id,
        "reporting_month": reporting_month,
        "candidate_count": len(candidates),
        "existing_batch": existing,
        "can_transfer": len(candidates) > 0 and (
            not existing or existing.get("status") not in ["SUCCESS", "WRITING"]
        ),
    }


@router.get("/month-end/pending", response_model=PendingOfficesResponse)
def get_pending_offices(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
):
    """Get offices with pending receipts for HQ transfer (Phase 13).
    
    Returns list of offices that have SENT receipts but no successful
    HQ transfer for the specified month.
    """
    _ensure_feature_enabled()
    _ensure_admin_only(current_user)
    
    reporting_month = f"{year:04d}-{month:02d}"
    writer_service = get_hq_transfer_writer_service()
    
    pending = writer_service.get_pending_offices(reporting_month)
    
    return PendingOfficesResponse(
        reporting_month=reporting_month,
        offices=[PendingOffice(**p) for p in pending],
    )
