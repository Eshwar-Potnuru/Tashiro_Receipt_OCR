"""Submission boundary wiring for Phase 3C (location + staff ledgers)."""

from __future__ import annotations

from typing import Dict, Iterable, List
import logging

from app.excel.branch_ledger_writer import BranchLedgerWriter
from app.excel.staff_ledger_writer import StaffLedgerWriter

logger = logging.getLogger(__name__)


class SummaryService:
    """Defines the send boundary for final submission."""

    def __init__(
        self,
        *,
        branch_writer: BranchLedgerWriter | None = None,
        staff_writer: StaffLedgerWriter | None = None,
    ) -> None:
        self.branch_writer = branch_writer or BranchLedgerWriter()
        self.staff_writer = staff_writer or StaffLedgerWriter()

    def send_receipts(self, receipts):
        """Write receipts to location (Format 02) and staff (Format 01) ledgers.

        HQ summary remains out of scope per Phase 2F. This entry point keeps
        deterministic ordering to avoid row-order churn across runs and isolates
        writer failures so one target cannot block the other.
        """

        logger.info(f"SUMMARY_SERVICE: send_receipts called with {len(list(receipts)) if receipts else 0} receipts")
        
        normalized: List = list(self._coerce_iterable(receipts))
        ordered = sorted(
            normalized,
            key=lambda r: (r.receipt_date is None, r.receipt_date or ""),
        )

        logger.info(f"SUMMARY_SERVICE: Processing {len(ordered)} receipts")
        
        results = []
        counts: Dict[str, int] = {"success": 0, "skipped": 0, "error": 0}

        for i, receipt in enumerate(ordered):
            logger.info(f"SUMMARY_SERVICE: Processing receipt {i+1}/{len(ordered)} - ID: {getattr(receipt, 'receipt_id', 'N/A')}")
            
            branch_res = self._safe_write(self.branch_writer.write_receipt, receipt)
            staff_res = self._safe_write(self.staff_writer.write_receipt, receipt)

            logger.info(f"SUMMARY_SERVICE: Receipt {i+1} - branch_res={branch_res}, staff_res={staff_res}")
            
            self._tally(branch_res, counts)
            self._tally(staff_res, counts)

            results.append(
                {
                    "receipt_id": str(getattr(receipt, "receipt_id", "")),
                    "branch": branch_res,
                    "staff": staff_res,
                }
            )

        logger.info(f"SUMMARY_SERVICE: Completed - counts={counts}")
        return {"processed": len(ordered), "counts": counts, "results": results}

    def _coerce_iterable(self, receipts) -> Iterable:
        if receipts is None:
            return []
        if isinstance(receipts, (list, tuple)):
            return receipts
        return [receipts]

    def _safe_write(self, writer, receipt):
        try:
            return writer(receipt)
        except Exception as exc:  # defensive isolation
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _tally(result: Dict[str, object], counts: Dict[str, int]) -> None:
        status = (result or {}).get("status")
        if status == "written":
            counts["success"] += 1
        elif status and str(status).startswith("skipped"):
            counts["skipped"] += 1
        elif status == "error":
            counts["error"] += 1
