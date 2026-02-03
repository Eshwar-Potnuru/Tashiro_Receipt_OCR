import uuid
from datetime import datetime, timedelta

import pytest

from app.repositories.draft_repository import DraftRepository


def test_delete_only_old_drafts_leaves_recent_and_sent():
    repo = DraftRepository(db_path=":memory:")
    conn = repo._get_connection()

    now = datetime.utcnow()
    old = now - timedelta(hours=48)

    rows = [
        (str(uuid.uuid4()), "{}", "DRAFT", old.isoformat(), old.isoformat()),
        (str(uuid.uuid4()), "{}", "SENT", old.isoformat(), old.isoformat()),
        (str(uuid.uuid4()), "{}", "DRAFT", now.isoformat(), now.isoformat()),
    ]

    conn.executemany(
        """
        INSERT INTO draft_receipts (draft_id, receipt_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    deleted = repo.delete_drafts_older_than(hours=24, statuses=["DRAFT"])
    assert deleted == 1

    cursor = conn.execute(
        "SELECT status, COUNT(*) FROM draft_receipts GROUP BY status ORDER BY status"
    )
    counts = {status: count for status, count in cursor.fetchall()}

    assert counts.get("DRAFT") == 1  # recent draft remains
    assert counts.get("SENT") == 1   # sent draft untouched


if __name__ == "__main__":
    pytest.main([__file__])
