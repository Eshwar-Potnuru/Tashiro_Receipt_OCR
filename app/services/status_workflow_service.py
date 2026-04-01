"""
Phase 12B-1: Status Workflow Service

Provides a clean separation between user-facing statuses and internal system statuses.

User-Facing Statuses (simple, PM-confirmed):
    - Draft: Receipt is editable, not yet sent
    - Submitted: Receipt has been sent, written to Excel

Internal Statuses (system-only, non-user-facing):
    - DraftStatus.DRAFT → user sees "Draft"
    - DraftStatus.SENT → user sees "Submitted"
    - DraftStatus.REVIEWED → user sees "Submitted" (internal HQ verification state)

This service:
    1. Maps internal statuses to user-facing display values
    2. Validates and executes status transitions
    3. Records transitions for audit purposes
    4. Enforces transition rules

Author: Phase 12B-1
Date: 2026-03-28
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import logging

from app.models.draft import DraftStatus

logger = logging.getLogger(__name__)


# =============================================================================
# USER-FACING STATUS ENUM (Simple: Draft / Submitted)
# =============================================================================

class UserFacingStatus(str, Enum):
    """
    User-facing receipt statuses.
    
    These are the ONLY statuses that should be shown to end users.
    Internal system statuses are mapped to these for display.
    
    PM-confirmed requirement: Keep user-facing statuses simple.
    """
    DRAFT = "Draft"
    SUBMITTED = "Submitted"


# Japanese display names for user-facing statuses
USER_FACING_STATUS_DISPLAY_JA: Dict[UserFacingStatus, str] = {
    UserFacingStatus.DRAFT: "下書き",
    UserFacingStatus.SUBMITTED: "提出済み",
}


# =============================================================================
# INTERNAL → USER-FACING MAPPING
# =============================================================================

# Map internal DraftStatus to user-facing UserFacingStatus
INTERNAL_TO_USER_FACING: Dict[DraftStatus, UserFacingStatus] = {
    DraftStatus.DRAFT: UserFacingStatus.DRAFT,
    DraftStatus.SENT: UserFacingStatus.SUBMITTED,
    DraftStatus.REVIEWED: UserFacingStatus.SUBMITTED,  # REVIEWED is internal-only, shows as Submitted
}


def get_user_facing_status(internal_status: DraftStatus) -> UserFacingStatus:
    """
    Convert internal DraftStatus to user-facing UserFacingStatus.
    
    Args:
        internal_status: The internal DraftStatus value
        
    Returns:
        The corresponding user-facing status
        
    Example:
        >>> get_user_facing_status(DraftStatus.SENT)
        <UserFacingStatus.SUBMITTED: 'Submitted'>
    """
    return INTERNAL_TO_USER_FACING.get(internal_status, UserFacingStatus.DRAFT)


def get_user_facing_status_display(
    internal_status: DraftStatus,
    language: str = "en"
) -> str:
    """
    Get the display string for a status in the specified language.
    
    Args:
        internal_status: The internal DraftStatus value
        language: "en" for English, "ja" for Japanese
        
    Returns:
        Human-readable status string
    """
    user_facing = get_user_facing_status(internal_status)
    
    if language == "ja":
        return USER_FACING_STATUS_DISPLAY_JA.get(user_facing, user_facing.value)
    return user_facing.value


# =============================================================================
# STATUS TRANSITION RULES
# =============================================================================

# Valid transitions for DraftStatus (internal)
# This is the source of truth for what transitions are allowed
VALID_INTERNAL_TRANSITIONS: Dict[DraftStatus, Set[DraftStatus]] = {
    DraftStatus.DRAFT: {
        DraftStatus.SENT,  # Submit/send the draft
    },
    DraftStatus.SENT: {
        DraftStatus.REVIEWED,  # HQ/Admin verification (internal-only)
        # Note: SENT → DRAFT is NOT allowed (immutable once sent)
    },
    DraftStatus.REVIEWED: {
        # Terminal state for now
        # Future: may allow re-review or other transitions
    },
}


def is_valid_transition(
    from_status: DraftStatus,
    to_status: DraftStatus
) -> bool:
    """
    Check if a status transition is valid.
    
    Args:
        from_status: Current status
        to_status: Target status
        
    Returns:
        True if the transition is allowed
    """
    if from_status == to_status:
        return True  # No-op transition is always valid
    
    valid_targets = VALID_INTERNAL_TRANSITIONS.get(from_status, set())
    return to_status in valid_targets


def get_valid_transitions(status: DraftStatus) -> Set[DraftStatus]:
    """
    Get all valid target statuses from the given status.
    
    Args:
        status: Current status
        
    Returns:
        Set of valid target statuses
    """
    return VALID_INTERNAL_TRANSITIONS.get(status, set()).copy()


# =============================================================================
# STATUS TRANSITION RECORD
# =============================================================================

@dataclass
class StatusTransitionRecord:
    """
    Record of a status transition for audit purposes.
    
    Attributes:
        draft_id: ID of the draft that changed
        from_status: Previous internal status
        to_status: New internal status
        from_user_facing: Previous user-facing status
        to_user_facing: New user-facing status
        triggered_by: Who triggered the transition (user_id or "SYSTEM")
        transition_time: When the transition occurred
        reason: Why the transition happened (e.g., "bulk_send", "hq_review")
        metadata: Additional context
    """
    draft_id: str
    from_status: DraftStatus
    to_status: DraftStatus
    from_user_facing: UserFacingStatus
    to_user_facing: UserFacingStatus
    triggered_by: str
    transition_time: datetime = field(default_factory=datetime.utcnow)
    reason: Optional[str] = None
    metadata: Optional[Dict] = None


# =============================================================================
# STATUS TRANSITION SERVICE
# =============================================================================

class StatusTransitionError(Exception):
    """Raised when a status transition is invalid."""
    
    def __init__(
        self,
        from_status: DraftStatus,
        to_status: DraftStatus,
        message: Optional[str] = None
    ):
        self.from_status = from_status
        self.to_status = to_status
        default_msg = f"Invalid transition: {from_status.value} → {to_status.value}"
        super().__init__(message or default_msg)


class StatusWorkflowService:
    """
    Service for managing status transitions.
    
    This service:
    1. Validates transitions before execution
    2. Records transitions for audit
    3. Provides user-facing status mapping
    
    Usage:
        >>> service = StatusWorkflowService()
        >>> service.validate_transition(DraftStatus.DRAFT, DraftStatus.SENT)
        True
        >>> record = service.record_transition(
        ...     draft_id="abc-123",
        ...     from_status=DraftStatus.DRAFT,
        ...     to_status=DraftStatus.SENT,
        ...     triggered_by="user-456",
        ...     reason="bulk_send"
        ... )
    """
    
    def __init__(self):
        self._transition_history: List[StatusTransitionRecord] = []
    
    def validate_transition(
        self,
        from_status: DraftStatus,
        to_status: DraftStatus,
        raise_on_invalid: bool = False
    ) -> bool:
        """
        Validate a status transition.
        
        Args:
            from_status: Current status
            to_status: Target status
            raise_on_invalid: If True, raise StatusTransitionError on invalid
            
        Returns:
            True if valid, False otherwise
            
        Raises:
            StatusTransitionError: If raise_on_invalid=True and transition invalid
        """
        valid = is_valid_transition(from_status, to_status)
        
        if not valid and raise_on_invalid:
            raise StatusTransitionError(from_status, to_status)
        
        return valid
    
    def record_transition(
        self,
        draft_id: str,
        from_status: DraftStatus,
        to_status: DraftStatus,
        triggered_by: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict] = None,
        validate: bool = True
    ) -> StatusTransitionRecord:
        """
        Record a status transition.
        
        Args:
            draft_id: ID of the draft
            from_status: Previous status
            to_status: New status
            triggered_by: Who triggered (user_id or "SYSTEM")
            reason: Why the transition happened
            metadata: Additional context
            validate: If True, validate before recording
            
        Returns:
            The transition record
            
        Raises:
            StatusTransitionError: If validate=True and transition is invalid
        """
        if validate:
            self.validate_transition(from_status, to_status, raise_on_invalid=True)
        
        record = StatusTransitionRecord(
            draft_id=draft_id,
            from_status=from_status,
            to_status=to_status,
            from_user_facing=get_user_facing_status(from_status),
            to_user_facing=get_user_facing_status(to_status),
            triggered_by=triggered_by,
            reason=reason,
            metadata=metadata,
        )
        
        self._transition_history.append(record)
        
        logger.info(
            f"Status transition recorded: {draft_id} "
            f"{from_status.value} → {to_status.value} "
            f"(user-facing: {record.from_user_facing.value} → {record.to_user_facing.value}) "
            f"by {triggered_by}"
        )
        
        return record
    
    def get_transition_history(
        self,
        draft_id: Optional[str] = None
    ) -> List[StatusTransitionRecord]:
        """
        Get transition history, optionally filtered by draft_id.
        
        Args:
            draft_id: If provided, filter to this draft only
            
        Returns:
            List of transition records
        """
        if draft_id:
            return [r for r in self._transition_history if r.draft_id == draft_id]
        return self._transition_history.copy()
    
    def get_user_facing_status(self, internal_status: DraftStatus) -> UserFacingStatus:
        """Get user-facing status from internal status."""
        return get_user_facing_status(internal_status)
    
    def get_user_facing_display(
        self,
        internal_status: DraftStatus,
        language: str = "en"
    ) -> str:
        """Get display string for status."""
        return get_user_facing_status_display(internal_status, language)


# =============================================================================
# MODULE-LEVEL SINGLETON (optional usage)
# =============================================================================

_default_service: Optional[StatusWorkflowService] = None


def get_status_workflow_service() -> StatusWorkflowService:
    """Get the default status workflow service instance."""
    global _default_service
    if _default_service is None:
        _default_service = StatusWorkflowService()
    return _default_service


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def is_user_facing_draft(internal_status: DraftStatus) -> bool:
    """Check if status appears as Draft to users."""
    return get_user_facing_status(internal_status) == UserFacingStatus.DRAFT


def is_user_facing_submitted(internal_status: DraftStatus) -> bool:
    """Check if status appears as Submitted to users."""
    return get_user_facing_status(internal_status) == UserFacingStatus.SUBMITTED


def can_user_edit(internal_status: DraftStatus) -> bool:
    """
    Check if user can edit a draft with this status.
    
    User-facing editing rules:
    - Draft → editable freely
    - Submitted → read-only (requires audit if editing allowed at all)
    """
    return is_user_facing_draft(internal_status)


def is_finalized(internal_status: DraftStatus) -> bool:
    """
    Check if the draft is finalized (written to Excel).
    
    Finalized means:
    - Status is SENT or REVIEWED
    - User sees "Submitted"
    - Data is in Excel
    """
    return internal_status in {DraftStatus.SENT, DraftStatus.REVIEWED}
