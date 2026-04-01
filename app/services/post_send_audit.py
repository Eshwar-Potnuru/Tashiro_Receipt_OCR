"""
Post-Send Audit Service for Phase 9.R.3

This module provides audit tracking for edits made to receipts after they have
been sent (status = SENT). Instead of blocking edits, the system now logs all
changes for compliance and traceability.

Usage:
    from app.services.post_send_audit import PostSendAuditService
    
    audit_service = PostSendAuditService()
    
    # Log an edit to a sent receipt
    audit_service.log_post_send_edit(
        draft_id="12345",
        field_name="total_amount",
        old_value="1000",
        new_value="1200",
        user_id="admin_user_1"
    )
    
    # Retrieve edit history
    edits = audit_service.get_post_send_edits("12345")
"""

import sqlite3
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

logger = logging.getLogger(__name__)


class PostSendAuditService:
    """
    Service for tracking edits made to receipts after they have been sent.
    
    Maintains an audit trail in the `post_send_edits` table with:
    - draft_id: The receipt being edited
    - field_name: Which field was modified
    - old_value: Previous value (JSON-stringified)
    - new_value: New value (JSON-stringified)
    - edited_by_user_id: User who made the edit
    - edited_at: Timestamp of the edit
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the PostSendAuditService.
        
        Args:
            db_path: Optional path to SQLite database. Defaults to app/Data/users.db
        """
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "Data", "users.db")
        
        self.db_path = db_path
        self._ensure_table_exists()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_table_exists(self) -> None:
        """Create the post_send_edits table if it doesn't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS post_send_edits (
                    edit_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    edited_by_user_id TEXT,
                    edited_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Create index for efficient lookups by draft_id
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_post_send_edits_draft_id 
                ON post_send_edits(draft_id)
            """)
            
            # Phase 11.B: Add Graph API audit columns (idempotent migration)
            self._migrate_phase11b_columns(cursor)
            
            conn.commit()
            logger.info("PostSendAuditService: post_send_edits table ensured")
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to create table: {e}")
            raise
        finally:
            conn.close()
    
    def _migrate_phase11b_columns(self, cursor) -> None:
        """Phase 11.B: Add Graph API tracking columns to post_send_edits table."""
        # Check existing columns
        cursor.execute("PRAGMA table_info(post_send_edits)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        
        # Define new columns for Phase 11.B
        new_columns = [
            ("file_id", "TEXT", "OneDrive file ID where cell was updated"),
            ("etag_before", "TEXT", "ETag of Excel file before update"),
            ("etag_after", "TEXT", "ETag of Excel file after update"),
            ("row_index", "INTEGER", "Row number in Excel sheet"),
            ("cell_address", "TEXT", "Excel cell address (e.g., 'A5')"),
            ("excel_write_confirmed", "INTEGER DEFAULT 0", "1 if Graph API confirmed write"),
            ("excel_write_error", "TEXT", "Error message if Excel write failed"),
            ("operation_type", "TEXT DEFAULT 'FIELD_EDIT'", "POST_SEND_EDIT, EXCEL_CELL_UPDATED, etc."),
        ]
        
        for col_name, col_type, col_desc in new_columns:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE post_send_edits ADD COLUMN {col_name} {col_type}")
                    logger.info(f"PostSendAuditService: Added column {col_name} ({col_desc})")
                except Exception as e:
                    # Column might already exist in some edge cases
                    logger.debug(f"PostSendAuditService: Column {col_name} migration: {e}")

    def log_post_send_edit(
        self,
        draft_id: Union[str, Any],
        field_name: str,
        old_value: Any,
        new_value: Any,
        user_id: Optional[str] = None,
        # Phase 11.B: Graph API tracking fields
        file_id: Optional[str] = None,
        etag_before: Optional[str] = None,
        etag_after: Optional[str] = None,
        row_index: Optional[int] = None,
        cell_address: Optional[str] = None,
        excel_write_confirmed: bool = False,
        excel_write_error: Optional[str] = None,
        operation_type: str = "POST_SEND_EDIT",
    ) -> str:
        """
        Log an edit made to a sent receipt.
        
        Args:
            draft_id: The draft/receipt ID being edited
            field_name: Name of the field being modified
            old_value: Previous value (will be JSON-stringified)
            new_value: New value (will be JSON-stringified)
            user_id: User ID making the edit
            file_id: Phase 11.B - OneDrive file ID where cell was updated
            etag_before: Phase 11.B - ETag of Excel file before update
            etag_after: Phase 11.B - ETag of Excel file after update
            row_index: Phase 11.B - Row number in Excel sheet
            cell_address: Phase 11.B - Excel cell address (e.g., 'A5')
            excel_write_confirmed: Phase 11.B - True if Graph API confirmed write
            excel_write_error: Phase 11.B - Error message if Excel write failed
            operation_type: Phase 11.B - POST_SEND_EDIT, EXCEL_CELL_UPDATED, etc.
            
        Returns:
            The edit_id of the logged entry
        """
        import json
        
        edit_id = str(uuid4())
        now = datetime.utcnow().isoformat()
        
        # Convert values to JSON strings for storage
        def to_json(val: Any) -> Optional[str]:
            if val is None:
                return None
            try:
                return json.dumps(val, default=str)
            except Exception:
                return str(val)
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO post_send_edits 
                (edit_id, draft_id, field_name, old_value, new_value, 
                 edited_by_user_id, edited_at, created_at,
                 file_id, etag_before, etag_after, row_index, cell_address,
                 excel_write_confirmed, excel_write_error, operation_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                edit_id,
                str(draft_id),
                field_name,
                to_json(old_value),
                to_json(new_value),
                user_id,
                now,
                now,
                # Phase 11.B: Graph API tracking fields
                file_id,
                etag_before,
                etag_after,
                row_index,
                cell_address,
                1 if excel_write_confirmed else 0,
                excel_write_error,
                operation_type,
            ))
            conn.commit()
            
            logger.info(
                f"PostSendAuditService: Logged edit for draft {draft_id}, "
                f"field={field_name}, edit_id={edit_id}, operation={operation_type}"
            )
            
            return edit_id
            
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to log edit: {e}")
            raise
        finally:
            conn.close()
    
    def log_batch_edits(
        self,
        draft_id: Union[str, Any],
        changes: Dict[str, tuple],
        user_id: Optional[str] = None
    ) -> List[str]:
        """
        Log multiple field edits in a single batch.
        
        Args:
            draft_id: The draft/receipt ID being edited
            changes: Dict mapping field_name -> (old_value, new_value)
            user_id: User ID making the edit
            
        Returns:
            List of edit_ids for the logged entries
        """
        edit_ids = []
        for field_name, (old_value, new_value) in changes.items():
            if old_value != new_value:  # Only log actual changes
                edit_id = self.log_post_send_edit(
                    draft_id=draft_id,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    user_id=user_id
                )
                edit_ids.append(edit_id)
        return edit_ids
    
    def get_post_send_edits(
        self,
        draft_id: Union[str, Any],
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve edit history for a sent receipt.
        
        Args:
            draft_id: The draft/receipt ID to get edits for
            limit: Optional maximum number of edits to return
            
        Returns:
            List of edit records, most recent first
        """
        import json
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = """
                SELECT edit_id, draft_id, field_name, old_value, new_value,
                       edited_by_user_id, edited_at, created_at
                FROM post_send_edits
                WHERE draft_id = ?
                ORDER BY edited_at DESC
            """
            
            if limit:
                query += f" LIMIT {int(limit)}"
            
            cursor.execute(query, (str(draft_id),))
            rows = cursor.fetchall()
            
            def from_json(val: Optional[str]) -> Any:
                if val is None:
                    return None
                try:
                    return json.loads(val)
                except Exception:
                    return val
            
            edits = []
            for row in rows:
                edits.append({
                    "edit_id": row["edit_id"],
                    "draft_id": row["draft_id"],
                    "field_name": row["field_name"],
                    "old_value": from_json(row["old_value"]),
                    "new_value": from_json(row["new_value"]),
                    "edited_by_user_id": row["edited_by_user_id"],
                    "edited_at": row["edited_at"],
                    "created_at": row["created_at"],
                })
            
            return edits
            
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to get edits: {e}")
            return []
        finally:
            conn.close()
    
    def has_post_send_edits(self, draft_id: Union[str, Any]) -> bool:
        """
        Check if a receipt has any post-send edits.
        
        Args:
            draft_id: The draft/receipt ID to check
            
        Returns:
            True if there are any post-send edits
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM post_send_edits WHERE draft_id = ?
            """, (str(draft_id),))
            row = cursor.fetchone()
            return row["count"] > 0 if row else False
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to check edits: {e}")
            return False
        finally:
            conn.close()
    
    def get_edit_count(self, draft_id: Union[str, Any]) -> int:
        """
        Get the number of post-send edits for a receipt.
        
        Args:
            draft_id: The draft/receipt ID to check
            
        Returns:
            Count of post-send edits
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM post_send_edits WHERE draft_id = ?
            """, (str(draft_id),))
            row = cursor.fetchone()
            return row["count"] if row else 0
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to get count: {e}")
            return 0
        finally:
            conn.close()

    def log_excel_cell_update(
        self,
        draft_id: Union[str, Any],
        field_name: str,
        old_value: Any,
        new_value: Any,
        user_id: Optional[str] = None,
        file_id: Optional[str] = None,
        etag_before: Optional[str] = None,
        etag_after: Optional[str] = None,
        row_index: Optional[int] = None,
        cell_address: Optional[str] = None,
        excel_write_confirmed: bool = False,
        excel_write_error: Optional[str] = None,
    ) -> str:
        """
        Log an Excel cell update following a post-send edit (Phase 11.B).
        
        This is a convenience wrapper around log_post_send_edit specifically
        for tracking changes made to Excel cells via Graph API.
        
        Args:
            draft_id: The draft/receipt ID being synced
            field_name: Receipt field that maps to this cell
            old_value: Previous cell value
            new_value: New cell value after update
            user_id: User who initiated the edit
            file_id: OneDrive file ID
            etag_before: ETag before the Graph API write
            etag_after: ETag after successful write (None if failed)
            row_index: Excel row number (1-based)
            cell_address: Cell address like 'C5'
            excel_write_confirmed: True if Graph API confirmed the write
            excel_write_error: Error message if write failed
            
        Returns:
            The edit_id of the logged entry
        """
        return self.log_post_send_edit(
            draft_id=draft_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            user_id=user_id,
            file_id=file_id,
            etag_before=etag_before,
            etag_after=etag_after,
            row_index=row_index,
            cell_address=cell_address,
            excel_write_confirmed=excel_write_confirmed,
            excel_write_error=excel_write_error,
            operation_type="EXCEL_CELL_UPDATED",
        )

    def log_excel_conflict(
        self,
        draft_id: Union[str, Any],
        field_name: str,
        draft_value: Any,
        excel_value: Any,
        user_id: Optional[str] = None,
        file_id: Optional[str] = None,
        row_index: Optional[int] = None,
    ) -> str:
        """
        Log when a conflict is detected between draft and Excel state (Phase 11.B).
        
        Called when the system detects that Excel was modified externally
        while a draft edit was in progress.
        
        Args:
            draft_id: The draft with the conflict
            field_name: Field where conflict was detected
            draft_value: Value in the draft
            excel_value: Current value in Excel
            user_id: User who encountered the conflict
            file_id: OneDrive file ID
            row_index: Excel row number
            
        Returns:
            The edit_id of the conflict log entry
        """
        import json
        return self.log_post_send_edit(
            draft_id=draft_id,
            field_name=field_name,
            old_value={"draft": draft_value, "excel": excel_value},
            new_value=None,  # No new value yet - pending resolution
            user_id=user_id,
            file_id=file_id,
            row_index=row_index,
            operation_type="EXCEL_CONFLICT_DETECTED",
        )

    def get_excel_updates(
        self,
        draft_id: Union[str, Any],
        confirmed_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get Excel cell update history for a draft (Phase 11.B).
        
        Args:
            draft_id: The draft to get updates for
            confirmed_only: If True, only return confirmed writes
            
        Returns:
            List of Excel update records
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = """
                SELECT edit_id, draft_id, field_name, old_value, new_value,
                       edited_by_user_id, edited_at, created_at,
                       file_id, etag_before, etag_after, row_index, cell_address,
                       excel_write_confirmed, excel_write_error, operation_type
                FROM post_send_edits
                WHERE draft_id = ? AND operation_type = 'EXCEL_CELL_UPDATED'
            """
            
            if confirmed_only:
                query += " AND excel_write_confirmed = 1"
            
            query += " ORDER BY edited_at DESC"
            
            cursor.execute(query, (str(draft_id),))
            rows = cursor.fetchall()
            
            import json
            def from_json(val: Optional[str]) -> Any:
                if val is None:
                    return None
                try:
                    return json.loads(val)
                except Exception:
                    return val
            
            updates = []
            for row in rows:
                updates.append({
                    "edit_id": row["edit_id"],
                    "draft_id": row["draft_id"],
                    "field_name": row["field_name"],
                    "old_value": from_json(row["old_value"]),
                    "new_value": from_json(row["new_value"]),
                    "edited_by_user_id": row["edited_by_user_id"],
                    "edited_at": row["edited_at"],
                    "file_id": row["file_id"],
                    "etag_before": row["etag_before"],
                    "etag_after": row["etag_after"],
                    "row_index": row["row_index"],
                    "cell_address": row["cell_address"],
                    "excel_write_confirmed": bool(row["excel_write_confirmed"]),
                    "excel_write_error": row["excel_write_error"],
                    "operation_type": row["operation_type"],
                })
            
            return updates
            
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to get Excel updates: {e}")
            return []
        finally:
            conn.close()

    def log_graph_send_result(
        self,
        draft_id: Union[str, Any],
        format_type: str,  # "format1" or "format2"
        result: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> str:
        """
        Log the result of a Graph API SEND operation (Phase 11B-1).
        
        This captures the initial write to Excel via Graph API during the
        send operation, tracking all metadata for later reconciliation.
        
        Args:
            draft_id: The draft being sent
            format_type: "format1" or "format2"
            result: Graph writer result dict with keys:
                - status: "written" | "error" | "skipped_*"
                - file_id: OneDrive file ID (if successful)
                - new_etag: ETag after write (if successful)
                - row: Row index written (if successful)
                - sheet: Worksheet name (if successful)
                - error: Error message (if failed)
                - failure_type: Error classification (if failed)
            user_id: User who initiated the send
            
        Returns:
            The edit_id of the logged entry
        """
        status = result.get("status", "unknown")
        file_id = result.get("file_id")
        new_etag = result.get("new_etag")
        row_index = result.get("row")
        worksheet_name = result.get("sheet")
        error_msg = result.get("error")
        failure_type = result.get("failure_type")
        
        # Determine operation outcome
        write_confirmed = status == "written"
        write_error = error_msg if not write_confirmed else None
        
        # Build summary for old_value (pre-send state = None)
        # and new_value (send result metadata)
        send_metadata = {
            "status": status,
            "file_id": file_id,
            "etag": new_etag,
            "row": row_index,
            "worksheet": worksheet_name,
            "format_type": format_type,
        }
        
        if failure_type:
            send_metadata["failure_type"] = failure_type
        if error_msg:
            send_metadata["error"] = error_msg
        
        return self.log_post_send_edit(
            draft_id=draft_id,
            field_name=f"{format_type}_send_result",
            old_value=None,  # No previous state for initial send
            new_value=send_metadata,
            user_id=user_id,
            file_id=file_id,
            etag_before=None,  # Not applicable for initial send
            etag_after=new_etag,
            row_index=row_index,
            cell_address=None,  # Full row, not a single cell
            excel_write_confirmed=write_confirmed,
            excel_write_error=write_error,
            operation_type="GRAPH_SEND_RESULT",
        )

    def get_send_audit_summary(
        self,
        draft_id: Union[str, Any],
    ) -> Dict[str, Any]:
        """
        Get a summary of all audit records for a draft (Phase 11B-1).
        
        Returns a structured summary including:
        - Initial send results (format1 and format2)
        - Post-send edit count
        - Excel conflict status
        - Latest sync state
        
        Args:
            draft_id: The draft to summarize
            
        Returns:
            Dict with audit summary
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get send results
            cursor.execute("""
                SELECT field_name, new_value, excel_write_confirmed, edited_at
                FROM post_send_edits
                WHERE draft_id = ? AND operation_type = 'GRAPH_SEND_RESULT'
                ORDER BY edited_at DESC
            """, (str(draft_id),))
            send_results = cursor.fetchall()
            
            # Get edit counts by type
            cursor.execute("""
                SELECT operation_type, COUNT(*) as count
                FROM post_send_edits
                WHERE draft_id = ?
                GROUP BY operation_type
            """, (str(draft_id),))
            type_counts = {row["operation_type"]: row["count"] for row in cursor.fetchall()}
            
            # Get conflict count
            conflict_count = type_counts.get("EXCEL_CONFLICT_DETECTED", 0)
            
            # Build summary
            import json
            summary = {
                "draft_id": str(draft_id),
                "format1_send": None,
                "format2_send": None,
                "post_send_edit_count": type_counts.get("POST_SEND_EDIT", 0),
                "excel_cell_update_count": type_counts.get("EXCEL_CELL_UPDATED", 0),
                "conflict_count": conflict_count,
                "has_unresolved_conflicts": conflict_count > 0,
            }
            
            for row in send_results:
                field_name = row["field_name"]
                try:
                    result_data = json.loads(row["new_value"]) if row["new_value"] else {}
                except:
                    result_data = {}
                    
                if field_name == "format1_send_result":
                    summary["format1_send"] = {
                        "confirmed": bool(row["excel_write_confirmed"]),
                        "timestamp": row["edited_at"],
                        **result_data,
                    }
                elif field_name == "format2_send_result":
                    summary["format2_send"] = {
                        "confirmed": bool(row["excel_write_confirmed"]),
                        "timestamp": row["edited_at"],
                        **result_data,
                    }
            
            return summary
            
        except Exception as e:
            logger.error(f"PostSendAuditService: Failed to get audit summary: {e}")
            return {"draft_id": str(draft_id), "error": str(e)}
        finally:
            conn.close()


# Module-level singleton for convenience
_default_service: Optional[PostSendAuditService] = None


def get_post_send_audit_service() -> PostSendAuditService:
    """Get the default PostSendAuditService instance."""
    global _default_service
    if _default_service is None:
        _default_service = PostSendAuditService()
    return _default_service
