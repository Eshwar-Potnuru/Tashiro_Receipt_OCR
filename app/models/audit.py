"""Phase 5A: Audit Event Model

Immutable audit log for draft receipt lifecycle tracking.

Key Principles:
- Append-only (no updates or deletes)
- Events are never modified after creation
- Captures who did what, when, and with what outcome
- Stored in separate SQLite database (audit.db)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Audit event types for receipt processing lifecycle.
    
    These events cover the complete draft lifecycle from creation
    through sending to Excel.
    """
    
    DRAFT_CREATED = "DRAFT_CREATED"
    """New draft saved from OCR or manual entry."""
    
    DRAFT_UPDATED = "DRAFT_UPDATED"
    """Existing draft modified (edit in RDV)."""
    
    SEND_ATTEMPTED = "SEND_ATTEMPTED"
    """Send operation initiated (may include multiple drafts)."""
    
    SEND_VALIDATION_FAILED = "SEND_VALIDATION_FAILED"
    """Draft failed READY-TO-SEND validation checks."""
    
    SEND_SUCCEEDED = "SEND_SUCCEEDED"
    """Draft successfully sent to Excel and marked as SENT."""
    
    SEND_FAILED = "SEND_FAILED"
    """Draft send failed (Excel write error or state update error)."""
    
    DRAFT_DELETED = "DRAFT_DELETED"
    """Draft deleted from system (note: Excel data remains if already sent)."""


class AuditEvent(BaseModel):
    """Immutable audit event record.
    
    Captures a single event in the draft receipt lifecycle with complete
    context for compliance and debugging.
    
    Attributes:
        event_id: Unique identifier for this audit event
        event_type: Type of operation being audited
        timestamp: When the business event occurred (UTC)
        actor: Who performed this action (user_id or "SYSTEM")
        draft_id: Target draft UUID (None for batch operations)
        data: Event-specific context (errors, results, changes)
        created_at: When this audit record was persisted
    
    Immutability:
        - Once created, audit events are never modified
        - No update() or delete() operations
        - Ensures tamper-proof audit trail
    
    Storage:
        - Persisted to audit.db SQLite database
        - data field stored as JSON blob
        - Indexed by draft_id, event_type, timestamp, actor
    
    Example:
        >>> event = AuditEvent(
        ...     event_type=AuditEventType.SEND_SUCCEEDED,
        ...     actor="SYSTEM",
        ...     draft_id="27a60a39-46aa-4b18-828b-8988911f8931",
        ...     data={
        ...         "sent_at": "2026-01-27T10:40:05Z",
        ...         "excel_result": {
        ...             "branch": {"status": "written", "row": 42},
        ...             "staff": {"status": "written", "row": 15}
        ...         }
        ...     }
        ... )
        >>> audit_repo.save_event(event)
    """
    
    event_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this audit event"
    )
    
    event_type: AuditEventType = Field(
        ...,
        description="Type of operation being audited"
    )
    
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the business event occurred (UTC timezone)"
    )
    
    actor: str = Field(
        ...,
        description="Who performed this action (user_id or 'SYSTEM' for Phase 5A)"
    )
    
    draft_id: Optional[UUID] = Field(
        None,
        description="Target draft UUID (None for batch operations like SEND_ATTEMPTED)"
    )
    
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific context (errors, validation results, Excel data)"
    )
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this audit record was persisted to database"
    )
    
    class Config:
        """Pydantic model configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
