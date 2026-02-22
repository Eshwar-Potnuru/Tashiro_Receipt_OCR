"""Phase 7A: HQ transfer batch tracking repository (SQLite-first).

Provides minimal batch lifecycle persistence for Office→HQ transfer scaffolding.
No Excel write logic is included here.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class HQTransferRepository:
    """SQLite repository for HQ transfer batches.

    Table: hq_transfer_batches
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            app_dir = Path(__file__).parent.parent
            data_dir = app_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "drafts.db")

        self.db_path = db_path
        self._memory_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hq_transfer_batches (
                    batch_id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    reporting_month TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL,
                    receipt_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_hq_transfer_batches_office_month_created
                ON hq_transfer_batches(office_id, reporting_month, created_at DESC)
                """
            )

            conn.commit()
        finally:
            if should_close:
                conn.close()

    def create_batch(
        self,
        *,
        batch_id: str,
        office_id: str,
        reporting_month: str,
        created_by_user_id: str,
    ) -> str:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            conn.execute(
                """
                INSERT INTO hq_transfer_batches (
                    batch_id, office_id, reporting_month, status,
                    created_at, created_by_user_id, receipt_count, error_message
                ) VALUES (?, ?, ?, 'CREATED', ?, ?, 0, NULL)
                """,
                (
                    batch_id,
                    office_id,
                    reporting_month,
                    datetime.utcnow().isoformat(),
                    created_by_user_id,
                ),
            )
            conn.commit()
            return batch_id
        finally:
            if should_close:
                conn.close()

    def get_latest_batch(self, office_id: str, reporting_month: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            row = conn.execute(
                """
                SELECT batch_id, office_id, reporting_month, status, created_at,
                       created_by_user_id, receipt_count, error_message
                FROM hq_transfer_batches
                WHERE office_id = ? AND reporting_month = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (office_id, reporting_month),
            ).fetchone()
            return dict(row) if row else None
        finally:
            if should_close:
                conn.close()

    def get_batch_by_id(self, batch_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            row = conn.execute(
                """
                SELECT batch_id, office_id, reporting_month, status, created_at,
                       created_by_user_id, receipt_count, error_message
                FROM hq_transfer_batches
                WHERE batch_id = ?
                LIMIT 1
                """,
                (batch_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            if should_close:
                conn.close()

    def get_latest_success_batch(self, office_id: str, reporting_month: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            row = conn.execute(
                """
                SELECT batch_id, office_id, reporting_month, status, created_at,
                       created_by_user_id, receipt_count, error_message
                FROM hq_transfer_batches
                WHERE office_id = ? AND reporting_month = ? AND status = 'SUCCESS'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (office_id, reporting_month),
            ).fetchone()
            return dict(row) if row else None
        finally:
            if should_close:
                conn.close()

    def is_success_batch_for_scope(self, batch_id: str, office_id: str, reporting_month: str) -> bool:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            row = conn.execute(
                """
                SELECT 1
                FROM hq_transfer_batches
                WHERE batch_id = ?
                  AND office_id = ?
                  AND reporting_month = ?
                  AND status = 'SUCCESS'
                LIMIT 1
                """,
                (batch_id, office_id, reporting_month),
            ).fetchone()
            return row is not None
        finally:
            if should_close:
                conn.close()

    def mark_drafts_transferred(self, draft_ids: List[str], batch_id: str) -> None:
        if not draft_ids:
            return

        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            placeholders = ",".join("?" * len(draft_ids))
            conn.execute(
                f"""
                UPDATE draft_receipts
                SET hq_status = 'SUCCESS',
                    hq_batch_id = ?,
                    hq_transferred_at = ?
                WHERE draft_id IN ({placeholders})
                """,
                [batch_id, datetime.utcnow().isoformat(), *draft_ids],
            )
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def count_batches(self, office_id: str, reporting_month: str) -> int:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM hq_transfer_batches
                WHERE office_id = ? AND reporting_month = ?
                """,
                (office_id, reporting_month),
            ).fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            if should_close:
                conn.close()

    def mark_writing(self, batch_id: str) -> None:
        self._update_status(batch_id=batch_id, status="WRITING", receipt_count=None, error_message=None)

    def mark_success(self, batch_id: str, receipt_count: int) -> None:
        self._update_status(
            batch_id=batch_id,
            status="SUCCESS",
            receipt_count=receipt_count,
            error_message=None,
        )

    def mark_failed(self, batch_id: str, error_message: str) -> None:
        self._update_status(
            batch_id=batch_id,
            status="FAILED",
            receipt_count=None,
            error_message=error_message,
        )

    def _update_status(
        self,
        *,
        batch_id: str,
        status: str,
        receipt_count: Optional[int],
        error_message: Optional[str],
    ) -> None:
        conn = self._get_connection()
        should_close = self._memory_conn is None
        try:
            if receipt_count is None:
                conn.execute(
                    """
                    UPDATE hq_transfer_batches
                    SET status = ?, error_message = ?
                    WHERE batch_id = ?
                    """,
                    (status, error_message, batch_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE hq_transfer_batches
                    SET status = ?, receipt_count = ?, error_message = ?
                    WHERE batch_id = ?
                    """,
                    (status, receipt_count, error_message, batch_id),
                )
            conn.commit()
        finally:
            if should_close:
                conn.close()
