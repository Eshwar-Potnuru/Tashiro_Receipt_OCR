"""Phase 5A: Audit Event Persistence Layer

SQLite-based repository for storing and retrieving audit events.

Design Decisions:
- Uses SQLite for simplicity and consistency with DraftRepository
- Separate database file at app/data/audit.db (isolation from drafts)
- Append-only operations (no updates or deletes)
- Connection-per-operation pattern (thread-safe)
- Retry logic for "database is locked" errors

Architecture:
- Mirrors DraftRepository pattern for consistency
- Automatic schema creation on first use
- Indexes on common query fields (draft_id, event_type, timestamp, actor)
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from app.models.audit import AuditEvent, AuditEventType


class AuditRepository:
    """SQLite-based persistence for audit events.
    
    This repository provides append-only storage for audit events with
    no business logic. Events are immutable once written.
    
    Storage Strategy:
        - SQLite database at app/data/audit.db (separate from drafts.db)
        - Single table: audit_events
        - Event data stored as JSON (Pydantic-serialized)
        - Automatic schema creation on first use
    
    Thread Safety:
        - Connection-per-operation pattern (no shared connections)
        - SQLite handles concurrency via file locks
        - Retry logic for "database is locked" errors (3 attempts)
    
    Immutability:
        - No update() or delete() methods
        - Audit events are write-once, read-many
        - Ensures tamper-proof audit trail
    """

    # Retry configuration for database lock handling
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 100  # milliseconds

    def __init__(self, db_path: Optional[str] = None):
        """Initialize repository with database path.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default
                    location at app/data/audit.db
        """
        if db_path is None:
            # Default: app/data/audit.db relative to project root
            app_dir = Path(__file__).parent.parent
            data_dir = app_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "audit.db")
        
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        """Create audit_events table and indexes if they don't exist.
        
        Schema:
            event_id: TEXT PRIMARY KEY (UUID as string)
            event_type: TEXT NOT NULL (AuditEventType enum value)
            timestamp: TEXT NOT NULL (ISO timestamp, when event occurred)
            actor: TEXT NOT NULL (who performed action, "SYSTEM" for Phase 5A)
            draft_id: TEXT (UUID as string, nullable for batch operations)
            data_json: TEXT NOT NULL (Pydantic-serialized event data)
            created_at: TEXT NOT NULL (ISO timestamp, when record was inserted)
        
        Indexes:
            - idx_audit_draft_id: Query events for a specific draft
            - idx_audit_event_type: Filter by event type
            - idx_audit_timestamp: Date range queries
            - idx_audit_actor: User activity queries (Phase 5B)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # Create table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    draft_id TEXT,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_draft_id 
                ON audit_events(draft_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_event_type 
                ON audit_events(event_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_events(timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_actor 
                ON audit_events(actor)
            """)
            
            conn.commit()
        finally:
            conn.close()

    def save_event(self, event: AuditEvent) -> None:
        """Save an audit event to the database.
        
        This is an append-only operation. Once saved, events cannot be
        modified or deleted.
        
        Args:
            event: AuditEvent to persist
        
        Raises:
            sqlite3.Error: If database write fails after all retries
        
        Note:
            Implements retry logic for "database is locked" errors.
            Will attempt up to MAX_RETRIES times with RETRY_DELAY_MS
            between attempts.
        """
        # Serialize event data to JSON
        data_json = json.dumps(event.data)
        
        # Convert UUIDs to strings, handle None for draft_id
        draft_id_str = str(event.draft_id) if event.draft_id else None
        
        # Retry loop for database lock handling
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                conn = sqlite3.connect(self.db_path)
                try:
                    conn.execute("""
                        INSERT INTO audit_events 
                        (event_id, event_type, timestamp, actor, draft_id, data_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(event.event_id),
                        event.event_type.value,
                        event.timestamp.isoformat(),
                        event.actor,
                        draft_id_str,
                        data_json,
                        event.created_at.isoformat(),
                    ))
                    conn.commit()
                    return  # Success, exit retry loop
                finally:
                    conn.close()
            
            except sqlite3.OperationalError as e:
                # Check if this is a "database is locked" error
                if "locked" in str(e).lower():
                    last_error = e
                    if attempt < self.MAX_RETRIES - 1:
                        # Sleep before retry
                        time.sleep(self.RETRY_DELAY_MS / 1000.0)
                        continue
                    # All retries exhausted
                    raise sqlite3.OperationalError(
                        f"Database locked after {self.MAX_RETRIES} attempts: {e}"
                    ) from e
                else:
                    # Other operational error, don't retry
                    raise

    def get_events_for_draft(
        self, 
        draft_id: UUID, 
        limit: int = 200
    ) -> List[AuditEvent]:
        """Retrieve all audit events for a specific draft.
        
        Returns events in reverse chronological order (most recent first).
        
        Args:
            draft_id: UUID of the draft to query
            limit: Maximum number of events to return (default 200)
        
        Returns:
            List of AuditEvent objects, ordered by timestamp DESC
        
        Example:
            >>> events = repo.get_events_for_draft(draft_id)
            >>> for event in events:
            ...     print(f"{event.timestamp}: {event.event_type}")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT event_id, event_type, timestamp, actor, draft_id, data_json, created_at
                FROM audit_events
                WHERE draft_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (str(draft_id), limit))
            
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    def get_recent_events(self, limit: int = 200) -> List[AuditEvent]:
        """Retrieve most recent audit events across all drafts.
        
        Returns events in reverse chronological order (most recent first).
        Useful for monitoring and debugging.
        
        Args:
            limit: Maximum number of events to return (default 200)
        
        Returns:
            List of AuditEvent objects, ordered by timestamp DESC
        
        Example:
            >>> events = repo.get_recent_events(limit=50)
            >>> for event in events:
            ...     print(f"{event.timestamp}: {event.event_type} - {event.actor}")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT event_id, event_type, timestamp, actor, draft_id, data_json, created_at
                FROM audit_events
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    def get_events_by_type(
        self,
        event_type: AuditEventType,
        limit: int = 200
    ) -> List[AuditEvent]:
        """Retrieve audit events of a specific type.
        
        Returns events in reverse chronological order (most recent first).
        
        Args:
            event_type: Type of events to retrieve
            limit: Maximum number of events to return (default 200)
        
        Returns:
            List of AuditEvent objects, ordered by timestamp DESC
        
        Example:
            >>> failures = repo.get_events_by_type(AuditEventType.SEND_FAILED)
            >>> print(f"Found {len(failures)} send failures")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT event_id, event_type, timestamp, actor, draft_id, data_json, created_at
                FROM audit_events
                WHERE event_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (event_type.value, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    def count_events(self) -> int:
        """Count total number of audit events.
        
        Useful for monitoring audit log growth and testing.
        
        Returns:
            Total number of audit events in database
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM audit_events")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def _row_to_event(self, row: sqlite3.Row) -> AuditEvent:
        """Convert a database row to an AuditEvent object.
        
        Args:
            row: SQLite row with audit event data
        
        Returns:
            AuditEvent object
        """
        # Deserialize data JSON
        data = json.loads(row["data_json"])
        
        # Parse timestamps
        timestamp = datetime.fromisoformat(row["timestamp"])
        created_at = datetime.fromisoformat(row["created_at"])
        
        # Parse draft_id (may be None)
        draft_id = UUID(row["draft_id"]) if row["draft_id"] else None
        
        # Create AuditEvent
        return AuditEvent(
            event_id=UUID(row["event_id"]),
            event_type=AuditEventType(row["event_type"]),
            timestamp=timestamp,
            actor=row["actor"],
            draft_id=draft_id,
            data=data,
            created_at=created_at,
        )
