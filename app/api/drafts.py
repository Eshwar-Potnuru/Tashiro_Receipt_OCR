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

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt
from app.services.draft_service import DraftService

# Create router
router = APIRouter(prefix="/api/drafts", tags=["drafts"])

# Singleton service instance
_draft_service: Optional[DraftService] = None


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
    """Response model for a single draft."""
    draft_id: UUID
    receipt: Receipt
    status: DraftStatus
    created_at: str
    updated_at: str
    sent_at: Optional[str] = None
    image_ref: Optional[str] = None
    is_valid: bool = Field(default=False, description="Whether draft is ready to send")
    validation_errors: List[str] = Field(default_factory=list, description="Validation error messages")

    @classmethod
    def from_draft(cls, draft: DraftReceipt, is_valid: bool = False, validation_errors: List[str] = None) -> DraftResponse:
        """Convert DraftReceipt to API response.
        
        Args:
            draft: DraftReceipt domain object
            is_valid: Whether draft passes READY-TO-SEND validation
            validation_errors: List of validation error messages
        """
        return cls(
            draft_id=draft.draft_id,
            receipt=draft.receipt,
            status=draft.status,
            created_at=draft.created_at.isoformat(),
            updated_at=draft.updated_at.isoformat(),
            sent_at=draft.sent_at.isoformat() if draft.sent_at else None,
            image_ref=draft.image_ref,
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
def save_draft(request: SaveDraftRequest) -> DraftResponse:
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
        draft = service.save_draft(request.receipt, image_ref=request.image_ref)
        return DraftResponse.from_draft(draft)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save draft: {str(exc)}",
        )


@router.get("", response_model=List[DraftResponse])
def list_drafts(status_filter: Optional[str] = None) -> List[DraftResponse]:
    """List all drafts, optionally filtered by status.
    
    Args:
        status_filter: Optional query parameter to filter by status
                      ("DRAFT" or "SENT"). If omitted, returns all drafts.
    
    Returns:
        List of DraftResponse objects with validation status, most recent first
    
    Example:
        GET /api/drafts              # All drafts
        GET /api/drafts?status_filter=DRAFT  # Only unsent drafts
        GET /api/drafts?status_filter=SENT   # Only sent drafts
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
    
    try:
        drafts = service.list_drafts(status=status_enum)
        
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
