"""Phase 4A: Draft Receipt Model & State Definition

This module defines the Draft/RDV (Receipt Draft View) data model for Phase 4.

Key Principles:
- DraftReceipt WRAPS the canonical Receipt model (does not replace it)
- Save operations create/update DraftReceipt with status=DRAFT
- Send operations transition DRAFT → SENT and trigger Excel writes
- SENT receipts are immutable (no further edits allowed)
- This model is UI-agnostic, Excel-agnostic, and persistence-agnostic

Phase 4A Scope: Data model and state contracts ONLY
- No UI implementation
- No Excel writing logic
- No persistence implementation
- No API endpoints

State Transition Rules:
  DRAFT → DRAFT  ✅ (edit and re-save)
  DRAFT → SENT   ✅ (bulk send operation)
  SENT → DRAFT   ❌ (immutable once sent)
  SENT → SENT    ❌ (no re-send)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.schema import Receipt


class DraftStatus(str, Enum):
    """Draft receipt lifecycle states.
    
    DRAFT:
        - Receipt is saved locally
        - Editable by user
        - NOT written to Excel
        - Can transition to SENT
    
    SENT:
        - Receipt has been submitted via bulk send
        - Written to Excel (Format 01 and Format 02)
        - Immutable (read-only, no further edits)
        - Terminal state (no further transitions)
    """

    DRAFT = "DRAFT"
    SENT = "SENT"


class DraftReceipt(BaseModel):
    """Wrapper model for Receipt with draft/send state management.
    
    This model wraps the canonical Receipt and adds state tracking for the
    Save/RDV/Bulk Send workflow introduced in Phase 4.
    
    Attributes:
        draft_id: Unique identifier for this draft (independent of receipt_id)
        receipt: The canonical Receipt data (Phase 2F locked contract)
        status: Current lifecycle state (DRAFT or SENT)
        created_at: Timestamp when draft was first created
        updated_at: Timestamp of last modification
        sent_at: Timestamp when status changed to SENT (None if still DRAFT)
    
    State Guarantees:
        - Save never writes to Excel (status remains DRAFT)
        - Send writes to Excel and transitions to SENT
        - SENT receipts cannot be modified or re-sent
        - Multiple DRAFT receipts can exist simultaneously (batch workflow)
    
    Persistence Notes:
        - Phase 4A does NOT implement storage (DB/file/in-memory)
        - Storage strategy will be decided in Phase 4B
        - This model is designed to be easily serializable for any backend
    
    Excel Write Boundary:
        - Only receipts with status=SENT should be in Excel
        - DraftReceipt.receipt contains the data written to Excel
        - Excel write operation happens during DRAFT → SENT transition
    """

    draft_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this draft (independent of receipt_id)",
    )
    
    receipt: Receipt = Field(
        ...,
        description="The canonical Receipt data wrapped by this draft",
    )
    
    status: DraftStatus = Field(
        default=DraftStatus.DRAFT,
        description="Current lifecycle state (DRAFT or SENT)",
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when draft was first created",
    )
    
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of last modification",
    )
    
    sent_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when status changed to SENT (None if still DRAFT)",
    )
    
    image_ref: Optional[str] = Field(
        default=None,
        description="Reference to source image (queue_id from analysis endpoint). "
                    "Links draft to uploaded image for RDV UI display and verification.",
    )
    
    image_data: Optional[str] = Field(
        default=None,
        description="Base64-encoded image data for Railway/cloud deployment. "
                    "Stores the actual image inline to avoid ephemeral filesystem issues.",
    )
    
    creator_user_id: Optional[str] = Field(
        default=None,
        description="Phase 5B.2: User ID of the user who created this draft. "
                    "NULL for drafts created before Phase 5B.2 or by unauthenticated users. "
                    "Stored as string (UUID) for compatibility with user.user_id.",
    )
    
    # Phase 5C-1: Failure Recovery & Retry Fields
    send_attempt_count: int = Field(
        default=0,
        description="Phase 5C-1: Number of send attempts for this draft. "
                    "Incremented before each send attempt. "
                    "0 = never attempted, 1+ = has been tried.",
    )
    
    last_send_attempt_at: Optional[datetime] = Field(
        default=None,
        description="Phase 5C-1: Timestamp of last send attempt. "
                    "Updated before each send. NULL if never attempted.",
    )
    
    last_send_error: Optional[str] = Field(
        default=None,
        description="Phase 5C-1: Last error message from failed send attempt. "
                    "Cleared on successful send. NULL if no errors or never attempted.",
    )

    class Config:
        """Pydantic configuration."""
        use_enum_values = False  # Keep enum instances, not strings

    def mark_as_sent(self) -> DraftReceipt:
        """Transition DRAFT → SENT (for bulk send operation).
        
        This is a helper method for state transition logic.
        Actual Excel writes happen in SummaryService (Phase 3 boundary).
        
        Returns:
            Updated DraftReceipt with status=SENT and sent_at timestamp
        
        Raises:
            ValueError: If receipt is already SENT (immutability violation)
        
        Note:
            This method does NOT write to Excel. It only updates the state.
            Phase 4D (Bulk Send) will coordinate state transition + Excel write.
        """
        if self.status == DraftStatus.SENT:
            raise ValueError(
                f"Cannot mark draft {self.draft_id} as sent: already SENT at {self.sent_at}"
            )
        
        self.status = DraftStatus.SENT
        self.sent_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        return self

    def update_receipt_data(self, updated_receipt: Receipt) -> DraftReceipt:
        """Update wrapped receipt data (only allowed in DRAFT state).
        
        This enables the edit-and-re-save workflow for draft receipts.
        
        Args:
            updated_receipt: New Receipt data with user corrections
        
        Returns:
            Updated DraftReceipt with new receipt data and updated timestamp
        
        Raises:
            ValueError: If receipt is SENT (immutability violation)
        
        Note:
            This method does NOT persist changes. Persistence layer (Phase 4B)
            will handle storage of updated DraftReceipt.
        """
        if self.status == DraftStatus.SENT:
            raise ValueError(
                f"Cannot update draft {self.draft_id}: already SENT (immutable)"
            )
        
        self.receipt = updated_receipt
        self.updated_at = datetime.utcnow()
        return self

    def is_draft(self) -> bool:
        """Check if receipt is in DRAFT state (editable)."""
        return self.status == DraftStatus.DRAFT

    def is_sent(self) -> bool:
        """Check if receipt is in SENT state (immutable)."""
        return self.status == DraftStatus.SENT


# ============================================================================
# State Transition Contract (Phase 4A Documentation)
# ============================================================================
#
# Allowed Transitions:
#
#   DRAFT → DRAFT  ✅
#     - User saves receipt (first time): new DraftReceipt created
#     - User edits and re-saves: DraftReceipt.updated_at updated
#     - No Excel write occurs
#     - update_receipt_data() method used
#
#   DRAFT → SENT  ✅
#     - User clicks "Send" on one or more DRAFT receipts
#     - Bulk send operation (Phase 4D) processes all selected drafts
#     - For each draft:
#         1. Validate receipt data
#         2. Call SummaryService.send_receipts([receipt])
#         3. If Excel write succeeds, call mark_as_sent()
#         4. Persist updated DraftReceipt
#     - mark_as_sent() method used
#
# Forbidden Transitions:
#
#   SENT → DRAFT  ❌
#     - SENT receipts are immutable
#     - Attempting to edit raises ValueError
#     - No mechanism to "unsend" a receipt
#
#   SENT → SENT  ❌
#     - Cannot re-send an already-sent receipt
#     - Prevents duplicate Excel writes
#     - mark_as_sent() raises ValueError if already SENT
#
# Excel Write Boundary:
#
#   Save (DRAFT):
#     - DraftReceipt created/updated in persistence layer
#     - NO Excel write
#     - Data only in draft storage (DB/file/memory)
#
#   Send (DRAFT → SENT):
#     - SummaryService.send_receipts() called (Phase 3 boundary)
#     - Excel write to Format 01 and Format 02
#     - Only after successful write: mark_as_sent() called
#     - DraftReceipt persisted with status=SENT
#
# Batch Semantics:
#
#   Multiple DRAFT receipts:
#     - Users can save 5-6 receipts before sending
#     - Each has independent draft_id
#     - All remain DRAFT until "Send" clicked
#
#   Bulk Send:
#     - All DRAFT receipts sent together in one operation
#     - Per-receipt error isolation (Phase 3 guarantee)
#     - Partial success allowed: some may succeed, some may fail
#     - Only successfully written receipts transition to SENT
#
# Persistence Strategy (Phase 4B):
#
#   Options to be decided:
#     - PostgreSQL database (recommended for production)
#     - SQLite (for development/testing)
#     - JSON file storage (simple but not concurrent-safe)
#     - In-memory (for testing only)
#
#   Phase 4A remains agnostic to storage implementation.
#
# ============================================================================
