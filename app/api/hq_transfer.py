"""Phase 7A-3: Internal-only HQ transfer trigger endpoints (env-flagged).

No UI exposure and no HQ Excel writer integration in this phase.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.repositories.hq_transfer_repository import HQTransferRepository
from app.services.hq_transfer_service import HQTransferService, compute_reporting_month
from app.utils.feature_flags import is_hq_transfer_enabled


logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/hq-transfer", tags=["hq-transfer"])

_hq_transfer_service: Optional[HQTransferService] = None
_hq_transfer_repository: Optional[HQTransferRepository] = None


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


def _ensure_feature_enabled() -> None:
    if not is_hq_transfer_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _ensure_admin_only(current_user: User) -> None:
    role = str(getattr(current_user, "role", "")).upper()
    if role != "ADMIN":
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
