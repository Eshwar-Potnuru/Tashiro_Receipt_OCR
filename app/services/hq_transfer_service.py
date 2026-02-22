"""Phase 7A: Office→HQ transfer scaffolding (SQLite-first).

Provides lock + batch lifecycle foundation for future HQ write implementation.
No Excel writes are performed in this phase.
"""

from __future__ import annotations

from datetime import datetime
import logging
import threading
from typing import Any, List
from uuid import uuid4

from app.models.draft import DraftReceipt, DraftStatus
from app.repositories.draft_repository import DraftRepository
from app.repositories.hq_transfer_repository import HQTransferRepository


_hq_transfer_lock = threading.Lock()
logger = logging.getLogger(__name__)


def compute_reporting_month(submitted_at: datetime) -> str:
    """Compute reporting month from transfer submission timestamp (YYYY-MM)."""
    return submitted_at.strftime("%Y-%m")


class HQTransferService:
    """Service for Phase 7A HQ transfer foundation.

    begin_hq_transfer currently performs lifecycle transitions only:
    CREATED -> WRITING -> SUCCESS
    """

    def __init__(
        self,
        repository: HQTransferRepository | None = None,
        draft_repository: DraftRepository | None = None,
    ):
        self.repository = repository or HQTransferRepository()
        self.draft_repository = draft_repository or DraftRepository()

    def get_transfer_candidates(self, location_id: str, reporting_month: str) -> List[DraftReceipt]:
        """Get SENT candidates for HQ transfer for a location and reporting month.

        Rules:
        - SENT status only
        - business_location_id must match location_id
        - exclude drafts already linked to a SUCCESS batch for same location/month
        """
        sent_drafts = self.draft_repository.list_all(status=DraftStatus.SENT, limit=None)

        candidates: List[DraftReceipt] = []
        for draft in sent_drafts:
            receipt_location = getattr(draft.receipt, "business_location_id", None)
            if receipt_location != location_id:
                continue

            existing_batch_id = getattr(draft, "hq_batch_id", None)
            if existing_batch_id and self.repository.is_success_batch_for_scope(
                batch_id=str(existing_batch_id),
                office_id=location_id,
                reporting_month=reporting_month,
            ):
                continue

            candidates.append(draft)

        return candidates

    def begin_hq_transfer(self, location_id: str, submitted_at: datetime, user: Any) -> str:
        """Begin HQ transfer stub with process-wide serialization.

        Phase 7A-2 behavior:
        - reporting_month is computed from submitted_at
        - if SUCCESS batch exists for location/month, return it (idempotent)
        - select SENT transfer candidates scoped by location
        - transition CREATED -> WRITING -> SUCCESS
        - persist receipt_count on success
        """
        reporting_month = compute_reporting_month(submitted_at)

        with _hq_transfer_lock:
            existing_success = self.repository.get_latest_success_batch(location_id, reporting_month)
            if existing_success:
                existing_batch_id = str(existing_success["batch_id"])
                logger.info(
                    "hq_transfer_idempotent batch_id=%s location_id=%s reporting_month=%s receipt_count=%s",
                    existing_batch_id,
                    location_id,
                    reporting_month,
                    existing_success.get("receipt_count", 0),
                )
                return existing_batch_id

            candidates = self.get_transfer_candidates(location_id, reporting_month)
            receipt_count = len(candidates)

            created_by_user_id = str(getattr(user, "user_id", "system"))
            batch_id = str(uuid4())
            self.repository.create_batch(
                batch_id=batch_id,
                office_id=location_id,
                reporting_month=reporting_month,
                created_by_user_id=created_by_user_id,
            )

            try:
                self.repository.mark_writing(batch_id)
                self.repository.mark_success(batch_id, receipt_count=receipt_count)
                self.repository.mark_drafts_transferred(
                    draft_ids=[str(draft.draft_id) for draft in candidates],
                    batch_id=batch_id,
                )
                logger.info(
                    "hq_transfer_success batch_id=%s location_id=%s reporting_month=%s receipt_count=%s",
                    batch_id,
                    location_id,
                    reporting_month,
                    receipt_count,
                )
            except Exception as exc:
                self.repository.mark_failed(batch_id, error_message=str(exc)[:1000])
                raise

        return batch_id
