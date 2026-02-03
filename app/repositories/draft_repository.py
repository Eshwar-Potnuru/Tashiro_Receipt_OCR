"""Phase 4B: Draft Receipt Persistence Layer

SQLite-based repository for storing and retrieving DraftReceipt objects.

Design Decisions:
- Uses SQLite for simplicity and ACID compliance
- Single database file at app/data/drafts.db
- JSON column for receipt data (leverages Pydantic serialization)
- Thread-safe with connection-per-operation pattern
- No business logic (pure data access layer)

Migration Path:
- Can easily migrate to PostgreSQL later by changing connection string
- Schema is simple and portable
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt


class DraftRepository:
    """SQLite-based persistence for DraftReceipt objects.
    
    This repository provides CRUD operations for draft receipts without
    any business logic. State transitions are handled by DraftService.
    
    Storage Strategy:
        - SQLite database at app/data/drafts.db
        - Single table: draft_receipts
        - Receipt data stored as JSON (Pydantic-serialized)
        - Automatic schema creation on first use
    
    Thread Safety:
        - Connection-per-operation pattern (no shared connections)
        - SQLite handles concurrency via file locks
        - Safe for single-user Phase 4B scope
    
    Future Enhancements (Phase 9):
        - Add user_id column for multi-user support
        - Add indexes for performance
        - Migrate to PostgreSQL for production scale
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize repository with database path.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default
                    location at app/data/drafts.db
        """
        if db_path is None:
            # Default: app/data/drafts.db relative to project root
            app_dir = Path(__file__).parent.parent
            data_dir = app_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "drafts.db")
        
        self.db_path = db_path
        
        # For :memory: databases, keep a persistent connection
        # (otherwise each new connection creates a fresh empty database)
        self._memory_conn = None
        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
        
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection.
        
        For :memory: databases, returns the persistent connection.
        For file databases, creates a new connection.
        """
        if self._memory_conn is not None:
            return self._memory_conn
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        """Create draft_receipts table if it doesn't exist.
        
        Schema:
            draft_id: TEXT PRIMARY KEY (UUID as string)
            receipt_json: TEXT (Pydantic-serialized Receipt)
            status: TEXT (DRAFT or SENT)
            created_at: TEXT (ISO timestamp)
            updated_at: TEXT (ISO timestamp)
            sent_at: TEXT (ISO timestamp, nullable)
            image_ref: TEXT (queue_id reference, nullable for backward compatibility)
            image_data: TEXT (base64-encoded image data for Railway/cloud deployment)
            creator_user_id: TEXT (Phase 5B.2: ownership tracking)
            send_attempt_count: INTEGER (Phase 5C-1: send retry count)
            last_send_attempt_at: TEXT (Phase 5C-1: last send attempt timestamp)
            last_send_error: TEXT (Phase 5C-1: last error message)
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        try:
            # Create table with all columns (including Phase 5B.2 and 5C-1)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS draft_receipts (
                    draft_id TEXT PRIMARY KEY,
                    receipt_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT,
                    image_ref TEXT,
                    image_data TEXT,
                    creator_user_id TEXT,
                    send_attempt_count INTEGER DEFAULT 0,
                    last_send_attempt_at TEXT,
                    last_send_error TEXT
                )
            """)
            
            # Migrate existing table if needed (add new columns)
            # This is safe: SQLite ignores ADD COLUMN if column exists
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN image_ref TEXT
                """)
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN image_data TEXT
                """)
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Phase 5B.2: Add creator_user_id for ownership tracking
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN creator_user_id TEXT
                """)
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Phase 5C-1: Add failure recovery fields
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN send_attempt_count INTEGER DEFAULT 0
                """)
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN last_send_attempt_at TEXT
                """)
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN last_send_error TEXT
                """)
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def save(self, draft: DraftReceipt) -> DraftReceipt:
        """Save or update a draft receipt.
        
        Uses INSERT OR REPLACE to handle both create and update operations.
        
        Args:
            draft: DraftReceipt to save
        
        Returns:
            The saved draft (same instance)
        
        Note:
            This is a pure persistence operation. State validation should
            be done by DraftService before calling this method.
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        try:
            # Serialize receipt to JSON
            receipt_json = json.dumps(draft.receipt.model_dump(mode="json"))
            
            # Phase 5D-1.1: Defensive coercion - ensure creator_user_id is string before SQL insert
            creator_user_id_str = str(draft.creator_user_id) if draft.creator_user_id is not None else None
            if isinstance(creator_user_id_str, UUID):
                creator_user_id_str = str(creator_user_id_str)
            
            conn.execute("""
                INSERT OR REPLACE INTO draft_receipts 
                (draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref, image_data, creator_user_id,
                 send_attempt_count, last_send_attempt_at, last_send_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(draft.draft_id),
                receipt_json,
                draft.status.value,
                draft.created_at.isoformat(),
                draft.updated_at.isoformat(),
                draft.sent_at.isoformat() if draft.sent_at else None,
                draft.image_ref,
                draft.image_data,
                creator_user_id_str,
                draft.send_attempt_count,
                draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,
                draft.last_send_error,
            ))
            conn.commit()
            return draft
        finally:
            if should_close:
                conn.close()

    def get_by_id(self, draft_id: UUID) -> Optional[DraftReceipt]:
        """Retrieve a draft by its ID.
        
        Args:
            draft_id: UUID of the draft to retrieve
        
        Returns:
            DraftReceipt if found, None otherwise
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref, image_data, creator_user_id,
                       send_attempt_count, last_send_attempt_at, last_send_error
                FROM draft_receipts
                WHERE draft_id = ?
            """, (str(draft_id),))
            
            row = cursor.fetchone()
            if row is None:
                return None
            
            return self._row_to_draft(row)
        finally:
            if should_close:
                conn.close()

    def list_all(self, status: Optional[DraftStatus] = None, user_id: Optional[str] = None, include_image_data: bool = False) -> List[DraftReceipt]:
        """List all drafts, optionally filtered by status and user.
        
        By default, excludes image_data field to keep response payload small.
        Image data is only loaded when fetching individual draft details OR when explicitly requested.
        
        Args:
            status: If provided, only return drafts with this status.
                   If None, return all drafts.
            user_id: If provided, only return drafts for this user.
                    If None, return drafts for all users.
            include_image_data: If True, includes base64 image_data in response.
                               Use for admin views that need image previews.
                               Default False to keep payload small.
        
        Returns:
            List of DraftReceipt objects, ordered by created_at descending
            (most recent first)
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        conn.row_factory = sqlite3.Row
        try:
            # Build query based on include_image_data flag
            if include_image_data:
                # Include image_data for admin views
                query_parts = ["""
                    SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref, image_data, creator_user_id,
                       send_attempt_count, last_send_attempt_at, last_send_error
                    FROM draft_receipts
                """]
            else:
                # Exclude image_data for list views to reduce payload
                query_parts = ["""
                    SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref, creator_user_id,
                       send_attempt_count, last_send_attempt_at, last_send_error
                    FROM draft_receipts
                """]
            params = []
            
            # Add WHERE conditions
            where_conditions = []
            if status is not None:
                where_conditions.append("status = ?")
                params.append(status.value)
            if user_id is not None:
                where_conditions.append("creator_user_id = ?")
                params.append(user_id)
            
            if where_conditions:
                query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            # Add ORDER BY
            query_parts.append("ORDER BY created_at DESC")
            
            query = "\n".join(query_parts)
            cursor = conn.execute(query, params)
            
            rows = cursor.fetchall()
            return [self._row_to_draft(row) for row in rows]
        finally:
            if should_close:
                conn.close()

    def delete(self, draft_id: UUID) -> bool:
        """Delete a draft by its ID.
        
        Args:
            draft_id: UUID of the draft to delete
        
        Returns:
            True if draft was deleted, False if not found
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        try:
            cursor = conn.execute("""
                DELETE FROM draft_receipts
                WHERE draft_id = ?
            """, (str(draft_id),))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if should_close:
                conn.close()

    def get_by_image_ref(self, image_ref: str) -> Optional[DraftReceipt]:
        """Retrieve a draft by its image reference.
        
        Used to prevent duplicate drafts for the same receipt image.
        
        Args:
            image_ref: Image reference (queue_id) to search for
        
        Returns:
            DraftReceipt if found, None otherwise
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref, image_data, creator_user_id,
                       send_attempt_count, last_send_attempt_at, last_send_error
                FROM draft_receipts
                WHERE image_ref = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (image_ref,))
            
            row = cursor.fetchone()
            if row is None:
                return None
            
            return self._row_to_draft(row)
        finally:
            if should_close:
                conn.close()

    def get_by_ids(self, draft_ids: List[UUID]) -> List[DraftReceipt]:
        """Retrieve multiple drafts by their IDs (for bulk operations).
        
        Args:
            draft_ids: List of draft UUIDs to retrieve
        
        Returns:
            List of DraftReceipt objects found (may be fewer than requested)
        """
        if not draft_ids:
            return []
        
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        conn.row_factory = sqlite3.Row
        try:
            # Create placeholders for IN clause
            placeholders = ",".join("?" * len(draft_ids))
            cursor = conn.execute(f"""
                SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref, image_data, creator_user_id,
                       send_attempt_count, last_send_attempt_at, last_send_error
                FROM draft_receipts
                WHERE draft_id IN ({placeholders})
            """, [str(draft_id) for draft_id in draft_ids])
            
            rows = cursor.fetchall()
            return [self._row_to_draft(row) for row in rows]
        finally:
            if should_close:
                conn.close()

    def _row_to_draft(self, row: sqlite3.Row) -> DraftReceipt:
        """Convert a database row to a DraftReceipt object.
        
        Args:
            row: SQLite row with draft data
        
        Returns:
            DraftReceipt object
        """
        # Deserialize receipt JSON
        receipt_data = json.loads(row["receipt_json"])
        receipt = Receipt.model_validate(receipt_data)
        
        # Parse timestamps
        created_at = datetime.fromisoformat(row["created_at"])
        updated_at = datetime.fromisoformat(row["updated_at"])
        sent_at = datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None
        
        # Get image_ref (may be None for legacy drafts created before Phase 4C-3)
        image_ref = row["image_ref"] if "image_ref" in row.keys() else None
        
        # Get image_data (may be None for legacy drafts or filesystem-based images)
        image_data = row["image_data"] if "image_data" in row.keys() else None
        
        # Phase 5B.2: Get creator_user_id (may be None for legacy drafts)
        creator_user_id = row["creator_user_id"] if "creator_user_id" in row.keys() else None
        
        # Phase 5C-1: Get failure recovery fields (may be None/0 for legacy drafts)
        send_attempt_count = row["send_attempt_count"] if "send_attempt_count" in row.keys() else 0
        last_send_attempt_at = (
            datetime.fromisoformat(row["last_send_attempt_at"]) 
            if "last_send_attempt_at" in row.keys() and row["last_send_attempt_at"] 
            else None
        )
        last_send_error = row["last_send_error"] if "last_send_error" in row.keys() else None
        
        # Create DraftReceipt
        return DraftReceipt(
            draft_id=UUID(row["draft_id"]),
            receipt=receipt,
            status=DraftStatus(row["status"]),
            created_at=created_at,
            updated_at=updated_at,
            sent_at=sent_at,
            image_ref=image_ref,
            image_data=image_data,
            creator_user_id=creator_user_id,
            send_attempt_count=send_attempt_count,
            last_send_attempt_at=last_send_attempt_at,
            last_send_error=last_send_error,
        )

    def count_by_status(self, status: DraftStatus) -> int:
        """Count drafts by status (useful for metrics/testing).
        
        Args:
            status: Status to count
        
        Returns:
            Number of drafts with given status
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        try:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM draft_receipts
                WHERE status = ?
            """, (status.value,))
            return cursor.fetchone()[0]
        finally:
            if should_close:
                conn.close()

    def clear_all(self) -> int:
        """Delete all drafts (for testing only).
        
        Returns:
            Number of drafts deleted
        
        Warning:
            This is a destructive operation. Use only in tests.
        """
        conn = self._get_connection()
        should_close = (self._memory_conn is None)
        try:
            cursor = conn.execute("DELETE FROM draft_receipts")
            conn.commit()
            return cursor.rowcount
        finally:
            if should_close:
                conn.close()
