"""Phase 4B: Draft Receipt API Endpoints

FastAPI routes for draft receipt management (backend only, no UI).

Endpoints:
- POST /api/drafts        - Save receipt as draft
- GET /api/drafts         - List all drafts
- GET /api/drafts/{id}    - Get specific draft
- PUT /api/drafts/{id}    - Update draft
- DELETE /api/drafts/{id} - Delete draft
- POST /api/drafts/send   - Send drafts to Excel (bulk)

Phase 4B Scope:
- Backend APIs only
- No UI implementation
- No Excel writes on save
- Send triggers Excel via SummaryService
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
import os
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Depends, Request
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.models.user import User

from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt
from app.services.draft_service import DraftService
from app.repositories.user_repository import UserRepository
import logging

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/drafts", tags=["drafts"])

# Singleton service instance
_draft_service: Optional[DraftService] = None
DEBUG_DRAFTS = os.getenv("DEBUG_DRAFTS", "").lower() in {"1", "true", "yes", "on"}


def get_draft_service() -> DraftService:
    """Get or create DraftService singleton."""
    global _draft_service
    if _draft_service is None:
        _draft_service = DraftService()
    return _draft_service


# ============================================================================
# Request/Response Models
# ============================================================================

class SaveDraftRequest(BaseModel):
    """Request body for saving a new draft."""
    receipt: Receipt = Field(..., description="Receipt data to save as draft")
    image_ref: Optional[str] = Field(
        None,
        description="Optional reference to source image (queue_id from /mobile/analyze). "
                    "Used to link draft to uploaded image for RDV UI."
    )
    image_data: Optional[str] = Field(
        None,
        description="Optional base64-encoded image data for Railway/cloud deployment. "
                    "Stores image inline to avoid ephemeral filesystem issues."
    )


class UpdateDraftRequest(BaseModel):
    """Request body for updating an existing draft."""
    receipt: Receipt = Field(..., description="Updated receipt data")


class SendDraftsRequest(BaseModel):
    """Request body for sending multiple drafts to Excel."""
    draft_ids: List[UUID] = Field(
        ...,
        description="List of draft IDs to send",
        min_length=1,
    )


class DraftResponse(BaseModel):
    """Response model for a single draft.

    Includes convenience flattened fields to make frontend consumption easier
    (e.g., `vendor`, `invoice_number`, `total_amount`) so templates do not
    need to navigate into `receipt` for common display values.
    """
    draft_id: UUID
    receipt: Receipt
    status: DraftStatus
    created_at: str
    updated_at: str
    sent_at: Optional[str] = None
    image_ref: Optional[str] = None
    image_data: Optional[str] = None

    # Convenience flattened fields for frontend
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    created_by: Optional[str] = None
    creator_login_id: Optional[str] = None  # Phase 5E.1: Human-readable login ID
    creator_name: Optional[str] = None  # Phase 5E.1: Display name
    user_email: Optional[str] = None
    total_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    receipt_date: Optional[str] = None
    send_attempt_count: int = 0
    last_send_error: Optional[str] = None

    is_valid: bool = Field(default=False, description="Whether draft is ready to send")
    validation_errors: List[str] = Field(default_factory=list, description="Validation error messages")

    model_config = {
        "json_encoders": {
            UUID: str,
            Decimal: str,
            datetime: lambda v: v.isoformat() if v else None,
        }
    }

    @classmethod
    def from_draft(cls, draft: DraftReceipt, is_valid: bool = False, validation_errors: List[str] = None) -> DraftResponse:
        """Convert DraftReceipt to API response.
        
        This populates both the raw `receipt` as well as a set of flattened
        convenience fields frontends commonly need for list displays.
        """
        # Extract common fields from nested receipt if available
        r = draft.receipt
        vendor = getattr(r, 'vendor', None)
        invoice_number = getattr(r, 'invoice_number', None) or getattr(r, 'invoice', None)
        total_amount = getattr(r, 'total_amount', None)
        tax_amount = getattr(r, 'tax_amount', None)
        receipt_date = getattr(r, 'date', None) or getattr(r, 'receipt_date', None)

        # Phase 5E.1: Creator info - lookup user details
        created_by = None
        creator_login_id = None
        creator_name = None
        user_email = None
        
        if draft.creator_user_id:
            created_by = str(draft.creator_user_id)
            # Lookup user info from repository
            try:
                from uuid import UUID as UUID_Type
                user_repo = UserRepository()
                user_uuid = UUID_Type(draft.creator_user_id) if isinstance(draft.creator_user_id, str) else draft.creator_user_id
                user = user_repo.get_user_by_id(user_uuid)
                if user:
                    creator_login_id = user.login_id
                    creator_name = user.name
                    user_email = user.email
            except Exception as e:
                # Graceful fallback if user lookup fails
                logger.warning(f"Failed to lookup user {draft.creator_user_id}: {e}")

        return cls(
            draft_id=draft.draft_id,
            receipt=draft.receipt,
            status=draft.status,
            created_at=draft.created_at.isoformat(),
            updated_at=draft.updated_at.isoformat(),
            sent_at=draft.sent_at.isoformat() if draft.sent_at else None,
            image_ref=draft.image_ref,
            image_data=draft.image_data,
            vendor=vendor,
            invoice_number=invoice_number,
            created_by=created_by,
            creator_login_id=creator_login_id,
            creator_name=creator_name,
            user_email=user_email,
            total_amount=total_amount,
            tax_amount=tax_amount,
            receipt_date=receipt_date.isoformat() if isinstance(receipt_date, datetime) else receipt_date,
            send_attempt_count=draft.send_attempt_count,
            last_send_error=draft.last_send_error,
            is_valid=is_valid,
            validation_errors=validation_errors or [],
        )


class SendDraftsResponse(BaseModel):
    """Response model for bulk send operation."""
    total: int = Field(..., description="Total drafts requested")
    sent: int = Field(..., description="Number successfully sent")
    failed: int = Field(..., description="Number failed")
    results: List[dict] = Field(..., description="Per-draft results")


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
def save_draft(
    request: SaveDraftRequest,
    current_user: User = Depends(get_current_user)
) -> DraftResponse:
    """Save a receipt as a draft (no Excel write).
    
    This creates a new draft with status=DRAFT. The receipt is stored in
    the draft database but NOT written to Excel.
    
    Phase 4 Workflow:
        Save → DRAFT status (no Excel)
        Send → SENT status (writes to Excel)
    
    Args:
        request: SaveDraftRequest with receipt data
    
    Returns:
        DraftResponse with created draft info
    
    Example:
        POST /api/drafts
        {
            "receipt": {
                "receipt_date": "2026-01-26",
                "vendor_name": "Test Vendor",
                "invoice_number": "INV-001",
                "total_amount": 1000.00,
                "tax_10_amount": 90.91,
                "tax_8_amount": 0.00,
                "business_location_id": "aichi",
                "staff_id": "staff_001"
            }
        }
    """
    service = get_draft_service()
    
    try:
        creator_user_id = str(current_user.user_id) if current_user else None
        draft = service.save_draft(
            request.receipt,
            image_ref=request.image_ref,
            image_data=request.image_data,
            creator_user_id=creator_user_id
        )
        return DraftResponse.from_draft(draft)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save draft: {str(exc)}",
        )


@router.get("", response_model=List[DraftResponse])
def list_drafts(
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user)
) -> List[DraftResponse]:
    """List all drafts for the current user, optionally filtered by status.
    
    Args:
        status_filter: Optional query parameter to filter by status
                      ("DRAFT" or "SENT"). If omitted, returns all drafts.
        current_user: Authenticated user from JWT token
    
    Returns:
        List of DraftResponse objects with validation status, most recent first
        
    Notes:
        - ADMIN/HQ roles get image_data included (for office view previews)
        - WORKER role gets image_data excluded (to reduce payload for workers)
    
    Example:
        GET /api/drafts              # All drafts for current user
        GET /api/drafts?status_filter=DRAFT  # Only unsent drafts for current user
        GET /api/drafts?status_filter=SENT   # Only sent drafts for current user
    """
    service = get_draft_service()
    
    # Parse status filter
    status_enum = None
    if status_filter:
        try:
            status_enum = DraftStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be DRAFT or SENT.",
            )
    
    # Phase 5D-1.1: Defensive coercion - ensure user_id is string
    user_id = str(current_user.user_id) if current_user else None
    if isinstance(user_id, UUID):
        user_id = str(user_id)
    
    # Phase 5D-3: Multi-user isolation - WORKER sees only their drafts, ADMIN/HQ see all
    filter_by_user = None
    if current_user.role == "WORKER":
        filter_by_user = user_id
    
    # Phase 5E.2: Do NOT include image_data in list endpoint to avoid memory issues
    # Image previews will be fetched on-demand via GET /api/drafts/{id}
    include_image_data = False
    
    if DEBUG_DRAFTS:
        print(f"DEBUG: list_drafts called by user_id={current_user.user_id}, role={current_user.role}, filtering by user_id={filter_by_user}, include_image_data={include_image_data}")

    try:
        drafts = service.list_drafts(status=status_enum, user_id=filter_by_user, include_image_data=include_image_data)
        
        # Add validation status to each draft
        responses = []
        for draft in drafts:
            is_valid, errors = service._validate_ready_to_send(draft)
            responses.append(DraftResponse.from_draft(draft, is_valid=is_valid, validation_errors=errors))
        
        return responses
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list drafts: {str(exc)}",
        )


@router.get("/{draft_id}", response_model=DraftResponse)
def get_draft(draft_id: UUID) -> DraftResponse:
    """Get a specific draft by ID.
    
    Args:
        draft_id: UUID of the draft to retrieve
    
    Returns:
        DraftResponse with draft info
    
    Raises:
        404: If draft not found
    
    Example:
        GET /api/drafts/123e4567-e89b-12d3-a456-426614174000
    """
    service = get_draft_service()
    
    draft = service.get_draft(draft_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft not found: {draft_id}",
        )
    
    return DraftResponse.from_draft(draft)


@router.put("/{draft_id}", response_model=DraftResponse)
def update_draft(draft_id: UUID, request: UpdateDraftRequest) -> DraftResponse:
    """Update an existing draft with new receipt data.
    
    Only allowed for drafts with status=DRAFT.
    SENT drafts are immutable and cannot be updated.
    
    Args:
        draft_id: UUID of the draft to update
        request: UpdateDraftRequest with new receipt data
    
    Returns:
        DraftResponse with updated draft info
    
    Raises:
        404: If draft not found
        400: If draft is already SENT (immutable)
    
    Example:
        PUT /api/drafts/123e4567-e89b-12d3-a456-426614174000
        {
            "receipt": {
                "receipt_date": "2026-01-27",
                "vendor_name": "Updated Vendor",
                ...
            }
        }
    """
    service = get_draft_service()
    
    try:
        draft = service.update_draft(draft_id, request.receipt)
        return DraftResponse.from_draft(draft)
    except ValueError as exc:
        # Draft not found or immutability violation
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update draft: {str(exc)}",
        )


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(draft_id: UUID):
    """Delete a draft by ID.
    
    Can delete drafts in any state (DRAFT or SENT).
    
    Args:
        draft_id: UUID of the draft to delete
    
    Raises:
        404: If draft not found
    
    Example:
        DELETE /api/drafts/123e4567-e89b-12d3-a456-426614174000
    """
    service = get_draft_service()
    
    deleted = service.delete_draft(draft_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft not found: {draft_id}",
        )


@router.get("/{draft_id}/validate")
def validate_draft(draft_id: UUID):
    """Validate a draft against READY-TO-SEND requirements.
    
    Phase 4D: UI validation endpoint.
    Returns validation status and any errors.
    
    Args:
        draft_id: UUID of the draft to validate
    
    Returns:
        {
            "valid": bool,
            "errors": List[str]
        }
    
    Raises:
        404: If draft not found
    
    Example:
        GET /api/drafts/123e4567-e89b-12d3-a456-426614174000/validate
    """
    service = get_draft_service()
    
    draft = service.get_draft(draft_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft not found: {draft_id}",
        )
    
    is_valid, errors = service._validate_ready_to_send(draft)
    
    return {
        "valid": is_valid,
        "errors": errors
    }


@router.post("/batch-upload")
async def batch_upload_receipts(
    request: Request,
    files: List[UploadFile] = File(...),
    ocr_engine: str = Form('auto'),
    current_user: User = Depends(get_current_user)
) -> dict:
    """Upload multiple receipt images and create drafts (Phase 5C-2)."""
    logger.info("Batch upload endpoint called: files=%d, engine=%s, user=%s", len(files), ocr_engine, getattr(current_user, 'user_id', None))
    if len(files) > 4:
        logger.warning("Batch upload rejected: too many files (%d)", len(files))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 4 files allowed per batch"
        )
    
    service = get_draft_service()
    
    # Inspect incoming form for diagnostics
    try:
        form = await request.form()
        logger.debug("Form keys received: %s", list(form.keys()))
        # Also log raw values (non-file fields) for debugging
        for k in list(form.keys()):
            if k != 'files':
                try:
                    logger.debug('Form value %s: %s', k, form.get(k))
                except Exception:
                    logger.debug('Form value %s: <unreadable>', k)
    except Exception:
        logger.debug("Failed to read request.form() for diagnostics")

    # Read all files
    images = []
    for file in files:
        content = await file.read()
        images.append((content, file.filename))

    logger.info("Uploaded filenames: %s", [file.filename for file in files])
    
    # Phase 5D-1.1: Defensive coercion - ensure creator_user_id is string
    creator_user_id = str(current_user.user_id) if current_user else None
    if isinstance(creator_user_id, UUID):
        creator_user_id = str(creator_user_id)
    
    try:
        result = service.create_drafts_from_images(
            images=images,
            creator_user_id=creator_user_id,
            engine_preference=ocr_engine
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch upload failed: {str(exc)}",
        )


@router.post("/debug-batch-upload")
async def debug_batch_upload_receipts(
    files: List[UploadFile] = File(...),
    ocr_engine: str = Form('auto')
) -> dict:
    """Debug-only batch upload bypassing auth (enabled via DEBUG_DRAFTS flag)."""
    if not DEBUG_DRAFTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    logger.info("Debug batch upload called: files=%d, engine=%s", len(files), ocr_engine)

    if len(files) > 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 4 files allowed per batch"
        )

    service = get_draft_service()
    images = []
    for file in files:
        content = await file.read()
        images.append((content, file.filename))

    logger.info("Debug: Uploaded filenames: %s", [file.filename for file in files])

    try:
        result = service.create_drafts_from_images(
            images=images,
            creator_user_id=None,
            engine_preference=ocr_engine
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Debug batch upload failed: {str(exc)}",
        )


@router.post("/send", response_model=SendDraftsResponse)
def send_drafts(request: SendDraftsRequest) -> SendDraftsResponse:
    """Send multiple drafts to Excel in bulk (DRAFT → SENT transition).
    
    This is the critical operation that:
    1. Validates all drafts are in DRAFT state
    2. Calls SummaryService to write to Excel (Format 01 & 02)
    3. Marks successfully sent drafts as SENT (immutable)
    4. Handles partial failures gracefully
    
    Phase 3 Integration:
        - Calls SummaryService.send_receipts() (Phase 3 boundary)
        - Excel writes happen during this operation
        - Per-receipt error isolation (Phase 3 guarantee)
    
    Args:
        request: SendDraftsRequest with list of draft IDs
    
    Returns:
        SendDraftsResponse with:
            - total: Number of drafts requested
            - sent: Number successfully sent
            - failed: Number that failed
            - results: Per-draft status details
    
    State Rules:
        - Only DRAFT → SENT is allowed
        - Already-SENT drafts return error
        - Missing drafts return error
        - Partial success is allowed and reported
    
    Example:
        POST /api/drafts/send
        {
            "draft_ids": [
                "123e4567-e89b-12d3-a456-426614174000",
                "223e4567-e89b-12d3-a456-426614174001"
            ]
        }
        
        Response:
        {
            "total": 2,
            "sent": 2,
            "failed": 0,
            "results": [
                {
                    "draft_id": "123e4567-e89b-12d3-a456-426614174000",
                    "status": "sent",
                    "excel_result": {...}
                },
                {
                    "draft_id": "223e4567-e89b-12d3-a456-426614174001",
                    "status": "sent",
                    "excel_result": {...}
                }
            ]
        }
    """
    service = get_draft_service()
    
    try:
        result = service.send_drafts(request.draft_ids)
        return SendDraftsResponse(**result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send drafts: {str(exc)}",
        )


