"""Phase 5A Step 3: Read-Only Audit API Endpoints

FastAPI routes for querying audit events (admin/debug/compliance).

Endpoints:
- GET /api/audits/draft/{draft_id}  - Get audit trail for specific draft
- GET /api/audits/recent            - Get recent audit events
- GET /api/audits/type/{event_type} - Get events by type

Security Model:
- Read-only (no POST/PUT/DELETE)
- No authentication yet (future: admin-only)
- Safe for debugging and compliance monitoring

Phase 5A Scope:
- Query-only APIs
- No pagination framework
- No UI changes
- No filtering by actor yet
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.audit import AuditEvent, AuditEventType
from app.repositories.audit_repository import AuditRepository

# Create router
router = APIRouter(prefix="/api/audits", tags=["audit"])

# Singleton repository instance
_audit_repository: Optional[AuditRepository] = None


def get_audit_repository() -> AuditRepository:
    """Get or create AuditRepository singleton."""
    global _audit_repository
    if _audit_repository is None:
        _audit_repository = AuditRepository()
    return _audit_repository


# ============================================================================
# Response Models
# ============================================================================

class AuditEventResponse(BaseModel):
    """Response model for audit event with JSON-safe serialization."""
    
    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Type of audit event")
    timestamp: str = Field(..., description="When event occurred (ISO 8601)")
    actor: str = Field(..., description="Who performed the action")
    draft_id: Optional[str] = Field(None, description="Target draft UUID (if applicable)")
    data: dict = Field(..., description="Event-specific metadata")
    created_at: str = Field(..., description="When event was written to audit log (ISO 8601)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "9e30ad46-1d71-4aed-942e-ea3faec480af",
                "event_type": "DRAFT_CREATED",
                "timestamp": "2026-01-28T09:16:41.141000+00:00",
                "actor": "SYSTEM",
                "draft_id": "f581dbfa-0db8-462b-9d19-9faa7d40068f",
                "data": {
                    "vendor_name": "LAWSON",
                    "total_amount": 1500.0,
                    "business_location_id": "aichi"
                },
                "created_at": "2026-01-28T09:16:41.141000+00:00"
            }
        }


def _audit_event_to_response(event: AuditEvent) -> AuditEventResponse:
    """Convert AuditEvent domain model to API response."""
    return AuditEventResponse(
        event_id=str(event.event_id) if not isinstance(event.event_id, str) else event.event_id,
        event_type=event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
        timestamp=event.timestamp.isoformat() if not isinstance(event.timestamp, str) else event.timestamp,
        actor=event.actor,
        draft_id=str(event.draft_id) if event.draft_id and not isinstance(event.draft_id, str) else event.draft_id,
        data=event.data,
        created_at=event.created_at.isoformat() if not isinstance(event.created_at, str) else event.created_at,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/draft/{draft_id}",
    response_model=List[AuditEventResponse],
    summary="Get audit trail for draft",
    description=(
        "Retrieve all audit events for a specific draft, ordered by timestamp "
        "descending (most recent first). Returns complete lifecycle history from "
        "creation to current state."
    ),
)
async def get_draft_audit_trail(
    draft_id: UUID,
    limit: int = Query(
        200,
        ge=1,
        le=1000,
        description="Maximum number of events to return (default 200, max 1000)"
    ),
) -> List[AuditEventResponse]:
    """Get audit trail for a specific draft.
    
    Args:
        draft_id: UUID of the draft to query
        limit: Maximum number of events to return
    
    Returns:
        List of audit events ordered by timestamp DESC (newest first)
    
    Example:
        GET /api/audits/draft/f581dbfa-0db8-462b-9d19-9faa7d40068f?limit=50
    """
    try:
        repository = get_audit_repository()
        events = repository.get_events_for_draft(draft_id, limit=limit)
        return [_audit_event_to_response(event) for event in events]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit events: {str(exc)}"
        )


@router.get(
    "/recent",
    response_model=List[AuditEventResponse],
    summary="Get recent audit events",
    description=(
        "Retrieve most recent audit events across all drafts, ordered by timestamp "
        "descending. Useful for monitoring, debugging, and compliance reviews."
    ),
)
async def get_recent_audit_events(
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of events to return (default 100, max 1000)"
    ),
) -> List[AuditEventResponse]:
    """Get recent audit events across all drafts.
    
    Args:
        limit: Maximum number of events to return
    
    Returns:
        List of audit events ordered by timestamp DESC (newest first)
    
    Example:
        GET /api/audits/recent?limit=50
    """
    try:
        repository = get_audit_repository()
        events = repository.get_recent_events(limit=limit)
        return [_audit_event_to_response(event) for event in events]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit events: {str(exc)}"
        )


@router.get(
    "/type/{event_type}",
    response_model=List[AuditEventResponse],
    summary="Get audit events by type",
    description=(
        "Retrieve audit events filtered by event type. Valid types: "
        "DRAFT_CREATED, DRAFT_UPDATED, DRAFT_DELETED, SEND_ATTEMPTED, "
        "SEND_VALIDATION_FAILED, SEND_SUCCEEDED, SEND_FAILED. "
        "Useful for troubleshooting specific operations."
    ),
)
async def get_audit_events_by_type(
    event_type: str,
    limit: int = Query(
        200,
        ge=1,
        le=1000,
        description="Maximum number of events to return (default 200, max 1000)"
    ),
) -> List[AuditEventResponse]:
    """Get audit events filtered by type.
    
    Args:
        event_type: Type of events to retrieve (e.g., SEND_FAILED)
        limit: Maximum number of events to return
    
    Returns:
        List of audit events matching the type, ordered by timestamp DESC
    
    Raises:
        HTTPException(400): If event_type is invalid
    
    Example:
        GET /api/audits/type/SEND_FAILED?limit=50
    """
    # Validate event type
    try:
        event_type_enum = AuditEventType(event_type)
    except ValueError:
        valid_types = [et.value for et in AuditEventType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid event_type: '{event_type}'. "
                f"Valid types: {', '.join(valid_types)}"
            )
        )
    
    try:
        repository = get_audit_repository()
        events = repository.get_events_by_type(event_type_enum, limit=limit)
        return [_audit_event_to_response(event) for event in events]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit events: {str(exc)}"
        )


@router.get(
    "/stats",
    summary="Get audit statistics",
    description="Get summary statistics about audit events (total count).",
)
async def get_audit_stats() -> dict:
    """Get audit event statistics.
    
    Returns:
        Dictionary with total event count and available event types
    
    Example:
        GET /api/audits/stats
        
        Response:
        {
          "total_events": 1234,
          "event_types": ["DRAFT_CREATED", "DRAFT_UPDATED", ...]
        }
    """
    try:
        repository = get_audit_repository()
        total = repository.count_events()
        event_types = [et.value for et in AuditEventType]
        
        return {
            "total_events": total,
            "event_types": event_types,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit statistics: {str(exc)}"
        )
