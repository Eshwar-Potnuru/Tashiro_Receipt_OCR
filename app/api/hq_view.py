"""Phase 7.2: HQ Admin read-only view endpoint.

Returns office-month batches with SENT receipts for HQ review.
Read-only: No writes, no regeneration, no Excel operations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.repositories.draft_repository import DraftRepository


logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/hq-view", tags=["hq-view"])


def _ensure_hq_or_admin(current_user: User) -> None:
    """Ensure user has HQ or ADMIN role (ADMIN allowed temporarily for Phase 7.2)."""
    role = str(getattr(current_user, "role", "")).upper()
    if role not in ("HQ", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. HQ or ADMIN role required.",
        )


class ReceiptDetail(BaseModel):
    """Receipt detail for HQ view."""
    draft_id: str
    receipt_date: Optional[str] = None
    vendor: Optional[str] = None
    total: Optional[float] = None
    staff_name: Optional[str] = None
    business_location: Optional[str] = None
    invoice_flag: Optional[str] = None
    tax_10: Optional[float] = None
    tax_8: Optional[float] = None
    tax_exempt: Optional[float] = None
    sent_at: Optional[str] = None
    sent_by: Optional[str] = None


class OfficeBatch(BaseModel):
    """Office-month batch grouping."""
    office: str
    month: str  # YYYYMM format
    month_display: str  # Display format like "2025年01月"
    sent_timestamp: Optional[str] = None
    receipt_count: int
    batch_id: Optional[str] = None
    receipts: List[ReceiptDetail] = Field(default_factory=list)


class HQViewResponse(BaseModel):
    """HQ view response with batches."""
    batches: List[OfficeBatch]
    total_receipts: int


def _parse_receipt_json(receipt_json: str) -> Dict[str, Any]:
    """Parse receipt JSON safely."""
    try:
        return json.loads(receipt_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _compute_month_key(date_str: Optional[str]) -> Optional[str]:
    """Compute YYYYMM month key from date string."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return f"{dt.year}{dt.month:02d}"
    except (ValueError, AttributeError):
        return None


def _compute_month_display(month_key: Optional[str]) -> str:
    """Compute display format from YYYYMM key."""
    if not month_key or len(month_key) != 6:
        return "Unknown Month"
    try:
        year = month_key[:4]
        month = month_key[4:6]
        return f"{year}年{month}月"
    except (ValueError, IndexError):
        return "Unknown Month"


@router.get("/batches", response_model=HQViewResponse)
def get_hq_batches(
    office: Optional[str] = None,
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get office-month batches for HQ view (read-only).
    
    Returns SENT receipts grouped by office and month.
    
    Query params:
        office: Optional filter by business_location
        month: Optional filter by YYYYMM month key
    """
    _ensure_hq_or_admin(current_user)
    
    logger.info(
        "hq_view_batches user_id=%s role=%s office=%s month=%s",
        getattr(current_user, "user_id", None),
        getattr(current_user, "role", None),
        office,
        month,
    )
    
    # Fetch all SENT drafts
    repo = DraftRepository()
    from app.models.draft import DraftStatus
    drafts_list = repo.list_all(status=DraftStatus.SENT, include_image_data=False, limit=None)
    
    # Convert DraftReceipt objects to dict for easier processing
    drafts = []
    for draft_obj in drafts_list:
        # Serialize receipt to dict
        receipt_dict = draft_obj.receipt.model_dump() if hasattr(draft_obj.receipt, 'model_dump') else draft_obj.receipt.dict()
        
        drafts.append({
            "draft_id": draft_obj.draft_id,
            "receipt": receipt_dict,
            "status": draft_obj.status,
            "sent_at": draft_obj.sent_at.isoformat() if draft_obj.sent_at else None,
            "sent_by_user_id": draft_obj.sent_by_user_id,
            "hq_batch_id": draft_obj.hq_batch_id,
        })
    
    # Group by office-month
    batches_dict: Dict[str, List[Any]] = {}
    
    for draft in drafts:
        receipt = draft["receipt"]
        
        # Extract grouping keys using correct Receipt model fields
        draft_office = receipt.get("business_location_id") or  "Unknown Office"
        receipt_date = receipt.get("receipt_date")  # ISO format YYYY-MM-DD
        draft_month = _compute_month_key(receipt_date) or "000000"
        
        # Apply filters
        if office and draft_office != office:
            continue
        if month and draft_month != month:
            continue
        
        # Group key
        batch_key = f"{draft_office}|{draft_month}"
        
        if batch_key not in batches_dict:
            batches_dict[batch_key] = []
        
        batches_dict[batch_key].append({
            "draft": draft,
            "receipt": receipt,
        })
    
    # Build response batches
    response_batches: List[OfficeBatch] = []
    total_receipts = 0
    
    for batch_key, items in batches_dict.items():
        office_name, month_key = batch_key.split("|", 1)
        
        # Get most recent sent_at for batch timestamp
        sent_timestamps = [
            item["draft"].get("sent_at")
            for item in items
            if item["draft"].get("sent_at")
        ]
        batch_sent_at = max(sent_timestamps) if sent_timestamps else None
        
        # Build receipt details
        receipt_details = []
        for item in items:
            draft = item["draft"]
            receipt = item["receipt"]
            
            receipt_details.append(ReceiptDetail(
                draft_id=str(draft.get("draft_id", "")),
                receipt_date=receipt.get("receipt_date"),  # ISO format
                vendor=receipt.get("vendor_name"),
                total=float(receipt.get("total_amount")) if receipt.get("total_amount") else None,
                staff_name=str(receipt.get("staff_id")) if receipt.get("staff_id") else None,  # Convert UUID to string
                business_location=str(receipt.get("business_location_id")) if receipt.get("business_location_id") else None,  # Convert UUID to string
                invoice_flag=None,  # Not in Receipt model
                tax_10=float(receipt.get("tax_10_amount")) if receipt.get("tax_10_amount") else None,
                tax_8=float(receipt.get("tax_8_amount")) if receipt.get("tax_8_amount") else None,
                tax_exempt=None,  # Not directly in Receipt model
                sent_at=draft.get("sent_at"),
                sent_by=str(draft.get("sent_by_user_id")) if draft.get("sent_by_user_id") else None,  # Convert UUID to string
            ))
        
        response_batches.append(OfficeBatch(
            office=office_name,
            month=month_key,
            month_display=_compute_month_display(month_key),
            sent_timestamp=batch_sent_at,
            receipt_count=len(receipt_details),
            batch_id=None,  # No batch_id yet (Phase 7A not triggered)
            receipts=receipt_details,
        ))
        
        total_receipts += len(receipt_details)
    
    # Sort batches by office and month (descending)
    response_batches.sort(key=lambda b: (b.office, b.month), reverse=True)
    
    return HQViewResponse(
        batches=response_batches,
        total_receipts=total_receipts,
    )


@router.get("/offices", response_model=List[str])
def get_offices(
    current_user: User = Depends(get_current_user),
):
    """Get unique office list for filter dropdown."""
    _ensure_hq_or_admin(current_user)
    
    repo = DraftRepository()
    from app.models.draft import DraftStatus
    drafts_list = repo.list_all(status=DraftStatus.SENT, include_image_data=False, limit=None)
    
    offices = set()
    for draft_obj in drafts_list:
        receipt_dict = draft_obj.receipt.model_dump() if hasattr(draft_obj.receipt, 'model_dump') else draft_obj.receipt.dict()
        office = receipt_dict.get("business_location_id") or "Unknown Office"
        offices.add(office)
    
    return sorted(list(offices))


@router.get("/months", response_model=List[str])
def get_months(
    current_user: User = Depends(get_current_user),
):
    """Get unique month list for filter dropdown (YYYYMM format)."""
    _ensure_hq_or_admin(current_user)
    
    repo = DraftRepository()
    from app.models.draft import DraftStatus
    drafts_list = repo.list_all(status=DraftStatus.SENT, include_image_data=False, limit=None)
    
    months = set()
    for draft_obj in drafts_list:
        receipt_dict = draft_obj.receipt.model_dump() if hasattr(draft_obj.receipt, 'model_dump') else draft_obj.receipt.dict()
        receipt_date = receipt_dict.get("receipt_date")  # ISO format YYYY-MM-DD
        month_key = _compute_month_key(receipt_date)
        if month_key:
            months.add(month_key)
    
    return sorted(list(months), reverse=True)
