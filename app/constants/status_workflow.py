"""
Status Workflow Constants (Phase 10 Foundation)

Defines the canonical status values and workflow transitions for receipts/drafts.

Workflow: DRAFT → SUBMITTED → APPROVED → SENT_TO_HQ
Special States: REGENERATED (after post-send edit)

Author: Phase 10 Foundation
Date: 2025-01-24
"""

from enum import Enum
from typing import Dict, List, Set, Optional


class ReceiptStatus(str, Enum):
    """
    Receipt/Draft status values.
    
    Workflow transitions:
        DRAFT → SUBMITTED: User submits receipt for review
        SUBMITTED → APPROVED: Reviewer approves receipt
        APPROVED → SENT_TO_HQ: System sends to HQ (wrote to Excel)
        SENT_TO_HQ → REGENERATED: Post-send edit requires regeneration
        
    Any status → REJECTED: Rejected by reviewer
    Any status → DRAFT: Returned for corrections
    """
    
    # Initial state - receipt created, can be edited freely
    DRAFT = "draft"
    
    # Submitted for review - waiting for approval
    SUBMITTED = "submitted"
    
    # Approved by reviewer - ready for HQ send
    APPROVED = "approved"
    
    # Sent to HQ (written to Excel via Graph API)
    SENT_TO_HQ = "sent_to_hq"
    
    # Regenerated after post-send edit
    REGENERATED = "regenerated"
    
    # Rejected by reviewer
    REJECTED = "rejected"
    
    # Legacy alias for backward compatibility
    SENT = "sent"  # Maps to SENT_TO_HQ
    REVIEWED = "reviewed"  # Maps to APPROVED


# Status display names (for UI)
STATUS_DISPLAY_NAMES: Dict[ReceiptStatus, str] = {
    ReceiptStatus.DRAFT: "下書き",  # Draft
    ReceiptStatus.SUBMITTED: "提出済み",  # Submitted
    ReceiptStatus.APPROVED: "承認済み",  # Approved
    ReceiptStatus.SENT_TO_HQ: "本社送信済み",  # Sent to HQ
    ReceiptStatus.REGENERATED: "再生成済み",  # Regenerated
    ReceiptStatus.REJECTED: "差戻し",  # Rejected/Returned
    ReceiptStatus.SENT: "送信済み",  # Sent (legacy)
    ReceiptStatus.REVIEWED: "確認済み",  # Reviewed (legacy)
}

STATUS_DISPLAY_NAMES_EN: Dict[ReceiptStatus, str] = {
    ReceiptStatus.DRAFT: "Draft",
    ReceiptStatus.SUBMITTED: "Submitted",
    ReceiptStatus.APPROVED: "Approved",
    ReceiptStatus.SENT_TO_HQ: "Sent to HQ",
    ReceiptStatus.REGENERATED: "Regenerated",
    ReceiptStatus.REJECTED: "Rejected",
    ReceiptStatus.SENT: "Sent",
    ReceiptStatus.REVIEWED: "Reviewed",
}


# Valid workflow transitions
# Maps current status → set of valid next statuses
VALID_TRANSITIONS: Dict[ReceiptStatus, Set[ReceiptStatus]] = {
    ReceiptStatus.DRAFT: {
        ReceiptStatus.SUBMITTED,
        ReceiptStatus.APPROVED,  # Direct approval path
        ReceiptStatus.SENT_TO_HQ,  # Direct send path (existing behavior)
    },
    ReceiptStatus.SUBMITTED: {
        ReceiptStatus.APPROVED,
        ReceiptStatus.REJECTED,
        ReceiptStatus.DRAFT,  # Return for corrections
    },
    ReceiptStatus.APPROVED: {
        ReceiptStatus.SENT_TO_HQ,
        ReceiptStatus.REJECTED,
        ReceiptStatus.DRAFT,  # Return for corrections
    },
    ReceiptStatus.SENT_TO_HQ: {
        ReceiptStatus.REGENERATED,  # Post-send edit
    },
    ReceiptStatus.REGENERATED: {
        ReceiptStatus.SENT_TO_HQ,  # Re-send after regeneration
    },
    ReceiptStatus.REJECTED: {
        ReceiptStatus.DRAFT,  # Return to draft for editing
        ReceiptStatus.SUBMITTED,  # Re-submit
    },
    # Legacy aliases follow same rules as their canonical equivalents
    ReceiptStatus.SENT: {
        ReceiptStatus.REGENERATED,
    },
    ReceiptStatus.REVIEWED: {
        ReceiptStatus.SENT_TO_HQ,
        ReceiptStatus.REJECTED,
        ReceiptStatus.DRAFT,
    },
}


# Statuses that indicate "finalized" (written to external system)
FINALIZED_STATUSES: Set[ReceiptStatus] = {
    ReceiptStatus.SENT_TO_HQ,
    ReceiptStatus.REGENERATED,
    ReceiptStatus.SENT,  # Legacy alias
}


# Statuses that allow free editing
EDITABLE_STATUSES: Set[ReceiptStatus] = {
    ReceiptStatus.DRAFT,
    ReceiptStatus.REJECTED,
}


# Statuses that allow editing with audit tracking (post-send edit)
AUDIT_EDIT_STATUSES: Set[ReceiptStatus] = {
    ReceiptStatus.SENT_TO_HQ,
    ReceiptStatus.REGENERATED,
    ReceiptStatus.SENT,  # Legacy alias
}


# Statuses that block deletion
DELETE_BLOCKED_STATUSES: Set[ReceiptStatus] = {
    ReceiptStatus.SENT_TO_HQ,
    ReceiptStatus.REGENERATED,
    ReceiptStatus.SENT,  # Legacy alias
}


def is_valid_transition(from_status: ReceiptStatus, to_status: ReceiptStatus) -> bool:
    """
    Check if a status transition is valid.
    
    Args:
        from_status: Current status
        to_status: Target status
        
    Returns:
        True if transition is allowed
    """
    valid_targets = VALID_TRANSITIONS.get(from_status, set())
    return to_status in valid_targets


def can_edit(status: ReceiptStatus, require_audit: bool = False) -> bool:
    """
    Check if a receipt with given status can be edited.
    
    Args:
        status: Current receipt status
        require_audit: If True, check if audit-tracked editing is required
        
    Returns:
        True if editing is allowed (with or without audit)
    """
    if status in EDITABLE_STATUSES:
        return True
    if require_audit and status in AUDIT_EDIT_STATUSES:
        return True
    return False


def requires_audit_for_edit(status: ReceiptStatus) -> bool:
    """
    Check if editing requires audit logging.
    
    Args:
        status: Current receipt status
        
    Returns:
        True if audit logging is required for edits
    """
    return status in AUDIT_EDIT_STATUSES


def can_delete(status: ReceiptStatus) -> bool:
    """
    Check if a receipt with given status can be deleted.
    
    Args:
        status: Current receipt status
        
    Returns:
        True if deletion is allowed
    """
    return status not in DELETE_BLOCKED_STATUSES


def is_finalized(status: ReceiptStatus) -> bool:
    """
    Check if a receipt has been finalized (sent to external system).
    
    Args:
        status: Current receipt status
        
    Returns:
        True if receipt has been finalized
    """
    return status in FINALIZED_STATUSES


def get_display_name(status: ReceiptStatus, language: str = "ja") -> str:
    """
    Get the display name for a status.
    
    Args:
        status: Status to get display name for
        language: Language code ("ja" or "en")
        
    Returns:
        Localized display name
    """
    if language == "en":
        return STATUS_DISPLAY_NAMES_EN.get(status, status.value)
    return STATUS_DISPLAY_NAMES.get(status, status.value)


def normalize_status(status: str) -> ReceiptStatus:
    """
    Normalize a status string to ReceiptStatus enum.
    
    Handles legacy status values and case-insensitive matching.
    
    Args:
        status: Status string to normalize
        
    Returns:
        Normalized ReceiptStatus
        
    Raises:
        ValueError: If status is not recognized
    """
    status_lower = status.lower().strip()
    
    # Direct enum match
    try:
        return ReceiptStatus(status_lower)
    except ValueError:
        pass
    
    # Legacy mappings
    legacy_map = {
        "sent": ReceiptStatus.SENT_TO_HQ,
        "reviewed": ReceiptStatus.APPROVED,
        "pending": ReceiptStatus.SUBMITTED,
        "processing": ReceiptStatus.SUBMITTED,
    }
    
    if status_lower in legacy_map:
        return legacy_map[status_lower]
    
    raise ValueError(f"Unknown status: {status}")


def get_status_color(status: ReceiptStatus) -> str:
    """
    Get the CSS color for a status (for UI).
    
    Args:
        status: Status to get color for
        
    Returns:
        CSS color class or color code
    """
    color_map = {
        ReceiptStatus.DRAFT: "#6c757d",  # Gray
        ReceiptStatus.SUBMITTED: "#007bff",  # Blue
        ReceiptStatus.APPROVED: "#28a745",  # Green
        ReceiptStatus.SENT_TO_HQ: "#17a2b8",  # Teal
        ReceiptStatus.REGENERATED: "#fd7e14",  # Orange
        ReceiptStatus.REJECTED: "#dc3545",  # Red
        ReceiptStatus.SENT: "#17a2b8",  # Teal (same as SENT_TO_HQ)
        ReceiptStatus.REVIEWED: "#28a745",  # Green (same as APPROVED)
    }
    return color_map.get(status, "#6c757d")
