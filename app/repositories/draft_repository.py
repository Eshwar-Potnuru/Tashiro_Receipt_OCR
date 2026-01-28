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
        self._init_schema()

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
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # Create table with image_ref column
            conn.execute("""
                CREATE TABLE IF NOT EXISTS draft_receipts (
                    draft_id TEXT PRIMARY KEY,
                    receipt_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT,
                    image_ref TEXT
                )
            """)
            
            # Migrate existing table if needed (add image_ref column)
            # This is safe: SQLite ignores ADD COLUMN if column exists
            try:
                conn.execute("""
                    ALTER TABLE draft_receipts ADD COLUMN image_ref TEXT
                """)
            except sqlite3.OperationalError:
                # Column already exists, safe to ignore
                pass
            
            conn.commit()
        finally:
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
        conn = sqlite3.connect(self.db_path)
        try:
            # Serialize receipt to JSON
            receipt_json = json.dumps(draft.receipt.model_dump(mode="json"))
            
            conn.execute("""
                INSERT OR REPLACE INTO draft_receipts 
                (draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(draft.draft_id),
                receipt_json,
                draft.status.value,
                draft.created_at.isoformat(),
                draft.updated_at.isoformat(),
                draft.sent_at.isoformat() if draft.sent_at else None,
                draft.image_ref,
            ))
            conn.commit()
            return draft
        finally:
            conn.close()

    def get_by_id(self, draft_id: UUID) -> Optional[DraftReceipt]:
        """Retrieve a draft by its ID.
        
        Args:
            draft_id: UUID of the draft to retrieve
        
        Returns:
            DraftReceipt if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref
                FROM draft_receipts
                WHERE draft_id = ?
            """, (str(draft_id),))
            
            row = cursor.fetchone()
            if row is None:
                return None
            
            return self._row_to_draft(row)
        finally:
            conn.close()

    def list_all(self, status: Optional[DraftStatus] = None) -> List[DraftReceipt]:
        """List all drafts, optionally filtered by status.
        
        Args:
            status: If provided, only return drafts with this status.
                   If None, return all drafts.
        
        Returns:
            List of DraftReceipt objects, ordered by created_at descending
            (most recent first)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if status is None:
                cursor = conn.execute("""
                    SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref
                    FROM draft_receipts
                    ORDER BY created_at DESC
                """)
            else:
                cursor = conn.execute("""
                    SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref
                    FROM draft_receipts
                    WHERE status = ?
                    ORDER BY created_at DESC
                """, (status.value,))
            
            rows = cursor.fetchall()
            return [self._row_to_draft(row) for row in rows]
        finally:
            conn.close()

    def delete(self, draft_id: UUID) -> bool:
        """Delete a draft by its ID.
        
        Args:
            draft_id: UUID of the draft to delete
        
        Returns:
            True if draft was deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                DELETE FROM draft_receipts
                WHERE draft_id = ?
            """, (str(draft_id),))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_by_image_ref(self, image_ref: str) -> Optional[DraftReceipt]:
        """Retrieve a draft by its image reference.
        
        Used to prevent duplicate drafts for the same receipt image.
        
        Args:
            image_ref: Image reference (queue_id) to search for
        
        Returns:
            DraftReceipt if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref
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
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Create placeholders for IN clause
            placeholders = ",".join("?" * len(draft_ids))
            cursor = conn.execute(f"""
                SELECT draft_id, receipt_json, status, created_at, updated_at, sent_at, image_ref
                FROM draft_receipts
                WHERE draft_id IN ({placeholders})
            """, [str(draft_id) for draft_id in draft_ids])
            
            rows = cursor.fetchall()
            return [self._row_to_draft(row) for row in rows]
        finally:
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
        
        # Create DraftReceipt
        return DraftReceipt(
            draft_id=UUID(row["draft_id"]),
            receipt=receipt,
            status=DraftStatus(row["status"]),
            created_at=created_at,
            updated_at=updated_at,
            sent_at=sent_at,
            image_ref=image_ref,
        )

    def count_by_status(self, status: DraftStatus) -> int:
        """Count drafts by status (useful for metrics/testing).
        
        Args:
            status: Status to count
        
        Returns:
            Number of drafts with given status
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM draft_receipts
                WHERE status = ?
            """, (status.value,))
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def clear_all(self) -> int:
        """Delete all drafts (for testing only).
        
        Returns:
            Number of drafts deleted
        
        Warning:
            This is a destructive operation. Use only in tests.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("DELETE FROM draft_receipts")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
