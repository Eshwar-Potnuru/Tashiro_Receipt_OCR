"""Phase 5A Step 2: Audit Logger Service

Provides best-effort audit event logging for draft lifecycle operations.

Key Principles:
- Audit failures NEVER block business operations
- All exceptions are caught and logged as warnings
- Uses "SYSTEM" as default actor (no auth in current system)
- Stores only safe metadata (no raw images, no secrets)
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from app.models.audit import AuditEvent, AuditEventType
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


def _serialize_for_audit(obj: Any) -> Any:
    """Convert objects to JSON-serializable format for audit data.
    
    Handles:
    - Decimal → float
    - UUID → str
    - datetime → ISO string
    - Recursively processes dicts and lists
    
    Args:
        obj: Object to serialize
    
    Returns:
        JSON-serializable version of object
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _serialize_for_audit(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize_for_audit(item) for item in obj]
    else:
        return obj


class AuditLogger:
    """Best-effort audit event logger for draft operations.
    
    This service wraps AuditRepository with error handling to ensure
    that audit failures never interrupt business operations. All audit
    logging is asynchronous from the user's perspective (they don't wait
    for audit writes to complete, and audit failures don't affect responses).
    
    Architecture:
        DraftService (business logic)
            ↓ calls
        AuditLogger (this class) ← error boundary
            ↓ calls
        AuditRepository ← persistence with retry logic
            ↓
        audit.db (SQLite)
    
    Error Handling:
        - All exceptions caught and logged as warnings
        - Original exception NOT re-raised
        - Business operations continue unaffected
    
    Actor Context:
        - Default actor is "SYSTEM" (no authentication currently)
        - Can be overridden per log() call for future auth integration
    
    Example:
        audit_logger = AuditLogger()
        
        # Business operation
        draft = create_draft(...)
        
        # Best-effort audit (failures are silent to caller)
        audit_logger.log(
            event_type=AuditEventType.DRAFT_CREATED,
            draft_id=draft.draft_id,
            data={"vendor_name": draft.receipt.vendor_name}
        )
        
        # If audit fails, draft creation still succeeded
    """
    
    DEFAULT_ACTOR = "SYSTEM"
    
    def __init__(self, repository: Optional[AuditRepository] = None):
        """Initialize audit logger.
        
        Args:
            repository: AuditRepository for persistence. If None, creates default.
        """
        self.repository = repository or AuditRepository()
    
    def log(
        self,
        event_type: AuditEventType,
        actor: Optional[str] = None,
        draft_id: Optional[UUID] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an audit event (best-effort, never raises).
        
        Builds an AuditEvent and persists it to audit.db. If any error occurs
        (database locked, disk full, etc.), logs a warning and returns without
        raising an exception.
        
        Args:
            event_type: Type of audit event (from AuditEventType enum)
            actor: Who performed the action (defaults to "SYSTEM")
            draft_id: Target draft UUID (optional, None for batch operations)
            data: Event-specific metadata dict (defaults to empty dict)
        
        Side Effects:
            - Creates audit event in audit.db (best-effort)
            - Logs warning on failure (does NOT raise)
        
        Thread Safety:
            - Safe to call from multiple threads
            - AuditRepository handles database locking with retry logic
        
        Example:
            # Log draft creation
            audit_logger.log(
                event_type=AuditEventType.DRAFT_CREATED,
                draft_id=draft.draft_id,
                data={
                    "vendor_name": "LAWSON",
                    "total_amount": 1500.0,
                    "business_location_id": "aichi"
                }
            )
            
            # Log send attempt (batch operation, no draft_id)
            audit_logger.log(
                event_type=AuditEventType.SEND_ATTEMPTED,
                data={"batch_size": 5, "draft_ids": ["...", "..."]}
            )
        """
        try:
            # Use defaults
            actor = actor or self.DEFAULT_ACTOR
            data = data or {}
            
            # Serialize data to handle Decimal, UUID, etc.
            serialized_data = _serialize_for_audit(data)
            
            # Build audit event
            event = AuditEvent(
                event_id=str(uuid4()),
                event_type=event_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor=actor,
                draft_id=str(draft_id) if draft_id else None,
                data=serialized_data,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            
            # Persist to audit.db (may retry on locks)
            self.repository.save_event(event)
            
        except Exception as exc:
            # Audit failure must NOT interrupt business operations
            logger.warning(
                f"Audit logging failed for event_type={event_type}, "
                f"draft_id={draft_id}: {exc}"
            )
            # Do NOT re-raise - this is a best-effort operation
