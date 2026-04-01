"""
Application Constants Package (Phase 10 Foundation)

Contains centralized constant definitions used throughout the application.

Modules:
    status_workflow: Receipt/draft status values and workflow transitions
"""

from .status_workflow import (
    ReceiptStatus,
    STATUS_DISPLAY_NAMES,
    STATUS_DISPLAY_NAMES_EN,
    VALID_TRANSITIONS,
    FINALIZED_STATUSES,
    EDITABLE_STATUSES,
    AUDIT_EDIT_STATUSES,
    DELETE_BLOCKED_STATUSES,
    is_valid_transition,
    can_edit,
    requires_audit_for_edit,
    can_delete,
    is_finalized,
    get_display_name,
    normalize_status,
    get_status_color,
)

__all__ = [
    "ReceiptStatus",
    "STATUS_DISPLAY_NAMES",
    "STATUS_DISPLAY_NAMES_EN",
    "VALID_TRANSITIONS",
    "FINALIZED_STATUSES",
    "EDITABLE_STATUSES",
    "AUDIT_EDIT_STATUSES",
    "DELETE_BLOCKED_STATUSES",
    "is_valid_transition",
    "can_edit",
    "requires_audit_for_edit",
    "can_delete",
    "is_finalized",
    "get_display_name",
    "normalize_status",
    "get_status_color",
]
