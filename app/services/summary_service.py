"""Submission boundary wiring for Phase 3C (location + staff ledgers).

Updated in Phase 9.R.1 to support Graph API-based writers for OneDrive storage.
Updated in Phase 9.R.2 to add Graph API writer for Format② (location ledger).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Iterable, List, Protocol
import logging
import threading

from app.excel.branch_ledger_writer import BranchLedgerWriter
from app.excel.staff_ledger_writer import StaffLedgerWriter

logger = logging.getLogger(__name__)
_excel_send_lock = threading.Lock()

# =============================================================================
# PHASE 9 STEP 1: SAFETY STABILIZATION (2026-03-20)
# =============================================================================
# Environment flag to enable Graph API writers.
#
# DEFAULT IS NOW FALSE (legacy/local writers) until Phase 10 live PoC passes.
#
# Background:
# - Graph API writers (format1_writer_graph.py, format2_writer_graph.py) are
#   fully implemented and preserved in the codebase.
# - However, they require valid Microsoft 365 credentials to function.
# - Before real client credentials are configured and Phase 10 PoC validation
#   passes, the safe default must be legacy/local openpyxl writers.
#
# To enable Graph API writers (requires valid Azure AD credentials):
#   Set USE_GRAPH_API_WRITERS=1 or USE_GRAPH_API_WRITERS=true
#
# This is NOT a rollback - all Graph code is preserved and ready for Phase 10.
# =============================================================================
USE_GRAPH_API_WRITERS = os.environ.get("USE_GRAPH_API_WRITERS", "false").lower() in ("1", "true", "yes")


class ReceiptWriter(Protocol):
    """Protocol for receipt writer implementations."""
    
    def write_receipt(self, receipt) -> Dict[str, object]:
        """Write a receipt and return status dict."""
        ...


class StaffLedgerWriterGraph:
    """Graph API wrapper for Format① staff ledger writer.
    
    Bridges the new Graph API format1_writer_graph to the existing
    SummaryService interface by adapting write_format1_row() to
    write_receipt().
    """
    
    def __init__(self, config_service=None):
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)
        
        # Lazy import to avoid circular dependencies
        self._write_format1_row = None
    
    def _get_writer(self):
        """Lazy load the Graph API writer function."""
        if self._write_format1_row is None:
            from app.services.format1_writer_graph import write_format1_row
            self._write_format1_row = write_format1_row
        return self._write_format1_row
    
    def write_receipt(self, receipt) -> Dict[str, object]:
        """Write receipt to OneDrive via Graph API.
        
        Adapts the Receipt model to the write_format1_row() interface.
        """
        if not receipt.staff_id:
            return {
                "status": "skipped_missing_staff_id",
                "reason": "staff_id required",
                "receipt_id": str(receipt.receipt_id)
            }
        
        try:
            # Extract year/month from receipt date
            receipt_date = receipt.receipt_date
            if receipt_date:
                try:
                    dt = datetime.fromisoformat(receipt_date)
                except Exception:
                    dt = datetime.now()
            else:
                dt = datetime.now()
            
            year = dt.year
            month = dt.month
            
            # Resolve staff display name
            staff_display = self._resolve_staff_name(receipt)
            
            # Build receipt data dict
            receipt_data = {
                "staff_id": receipt.staff_id,
                "receipt_date": receipt.receipt_date,
                "vendor_name": receipt.vendor_name,
                "memo": receipt.memo,
                "total_amount": receipt.total_amount,
                "invoice_number": receipt.invoice_number,
                "tax_10_amount": receipt.tax_10_amount,
                "tax_8_amount": receipt.tax_8_amount,
                "account_title": receipt.account_title,
                "receipt_id": str(receipt.receipt_id),
            }
            
            # Call Graph API writer
            write_fn = self._get_writer()
            result = write_fn(
                receipt_data=receipt_data,
                office=receipt.business_location_id or "unknown",
                staff=staff_display or receipt.staff_id,
                year=year,
                month=month,
                user_id="system"  # Could be enhanced to pass actual user
            )
            
            return result
            
        except Exception as exc:
            self.logger.exception("Failed to write staff ledger via Graph API")
            return {
                "status": "error",
                "error": str(exc),
                "staff": receipt.staff_id,
                "failure_type": getattr(exc, 'failure_type', None) and exc.failure_type.value or "unknown"
            }
    
    def _resolve_staff_name(self, receipt) -> str:
        """Resolve staff display name from ID."""
        if not receipt.staff_id:
            return None
        
        if self.config_service and receipt.business_location_id:
            try:
                staff_list = self.config_service.get_staff_for_location(
                    receipt.business_location_id
                )
                for staff in staff_list:
                    if staff.get("id") == receipt.staff_id:
                        return staff.get("name") or receipt.staff_id
            except Exception:
                pass
        
        return receipt.staff_id


class BranchLedgerWriterGraph:
    """Graph API wrapper for Format② location ledger writer.
    
    Bridges the new Graph API format2_writer_graph to the existing
    SummaryService interface by adapting write_format2_row() to
    write_receipt().
    
    Added in Phase 9.R.2.
    """
    
    def __init__(self, config_service=None):
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)
        
        # Lazy import to avoid circular dependencies
        self._write_format2_row = None
    
    def _get_writer(self):
        """Lazy load the Graph API writer function."""
        if self._write_format2_row is None:
            from app.services.format2_writer_graph import write_format2_row
            self._write_format2_row = write_format2_row
        return self._write_format2_row
    
    def write_receipt(self, receipt) -> Dict[str, object]:
        """Write receipt to OneDrive via Graph API.
        
        Adapts the Receipt model to the write_format2_row() interface.
        """
        if not receipt.business_location_id:
            return {
                "status": "skipped_missing_location_id",
                "reason": "business_location_id required",
                "receipt_id": str(receipt.receipt_id)
            }
        
        if not receipt.receipt_date:
            return {
                "status": "skipped_missing_date",
                "reason": "receipt_date required",
                "receipt_id": str(receipt.receipt_id)
            }
        
        try:
            # Extract year/month from receipt date
            receipt_date = receipt.receipt_date
            try:
                dt = datetime.fromisoformat(receipt_date)
            except Exception:
                dt = datetime.now()
            
            year = dt.year
            month = dt.month
            
            # Resolve staff display name
            staff_display = self._resolve_staff_name(receipt)
            
            # Build receipt data dict
            receipt_data = {
                "business_location_id": receipt.business_location_id,
                "receipt_date": receipt.receipt_date,
                "vendor_name": receipt.vendor_name,
                "memo": receipt.memo,
                "total_amount": receipt.total_amount,
                "invoice_number": receipt.invoice_number,
                "tax_10_amount": receipt.tax_10_amount,
                "tax_8_amount": receipt.tax_8_amount,
                "account_title": receipt.account_title,
                "staff_name": staff_display,
                "receipt_id": str(receipt.receipt_id),
            }
            
            # Call Graph API writer
            write_fn = self._get_writer()
            result = write_fn(
                receipt_data=receipt_data,
                office=receipt.business_location_id,
                year=year,
                month=month,
                user_id="system",  # Could be enhanced to pass actual user
                staff_display=staff_display
            )
            
            return result
            
        except Exception as exc:
            self.logger.exception("Failed to write location ledger via Graph API")
            return {
                "status": "error",
                "error": str(exc),
                "location": receipt.business_location_id,
                "failure_type": getattr(exc, 'failure_type', None) and exc.failure_type.value or "unknown"
            }
    
    def _resolve_staff_name(self, receipt) -> str:
        """Resolve staff display name from ID."""
        if not receipt.staff_id:
            return None
        
        if self.config_service and receipt.business_location_id:
            try:
                staff_list = self.config_service.get_staff_for_location(
                    receipt.business_location_id
                )
                for staff in staff_list:
                    if staff.get("id") == receipt.staff_id:
                        return staff.get("name") or receipt.staff_id
            except Exception:
                pass
        
        return receipt.staff_id


class SummaryService:
    """Defines the send boundary for final submission.
    
    Supports both local openpyxl writers (default) and Graph API writers
    (enabled via USE_GRAPH_API_WRITERS environment variable).
    
    Updated in Phase 9.R.2 to support Graph API for both Format① (staff)
    and Format② (location) ledgers.
    """

    def __init__(
        self,
        *,
        branch_writer: ReceiptWriter | None = None,
        staff_writer: ReceiptWriter | None = None,
        use_graph_api: bool | None = None,
    ) -> None:
        # Determine whether to use Graph API writers
        if use_graph_api is None:
            use_graph_api = USE_GRAPH_API_WRITERS
        
        if use_graph_api:
            # Use Graph API writers for both ledgers
            logger.info("SummaryService: Using Graph API for Format① (staff) and Format② (location) ledgers")
            
            if branch_writer is None:
                self.branch_writer = BranchLedgerWriterGraph()
            else:
                self.branch_writer = branch_writer
            
            if staff_writer is None:
                self.staff_writer = StaffLedgerWriterGraph()
            else:
                self.staff_writer = staff_writer
            
            # Graph API writers use safe_write() for locking - no global lock needed
            self._use_graph_api = True
        else:
            # Use local openpyxl writers (default)
            self.branch_writer = branch_writer or BranchLedgerWriter()
            self.staff_writer = staff_writer or StaffLedgerWriter()
            
            # Local writers need the global lock for serialization
            self._use_graph_api = False

    def send_receipts(self, receipts):
        """Write receipts to location (Format 02) and staff (Format 01) ledgers.

        HQ summary remains out of scope per Phase 2F. This entry point keeps
        deterministic ordering to avoid row-order churn across runs and isolates
        writer failures so one target cannot block the other.
        
        Locking behavior (Phase 9.R.2):
        - Graph API mode: Locking handled by conflict_resolver.safe_write()
        - Local mode: Uses _excel_send_lock for serialization
        """

        normalized: List = list(self._coerce_iterable(receipts))
        logger.info(f"SUMMARY_SERVICE: send_receipts called with {len(normalized)} receipts")

        # Graph API writers use safe_write() with ETag-based locking internally
        # Local writers need the global lock for serialization
        if self._use_graph_api:
            return self._process_receipts(normalized)
        else:
            with _excel_send_lock:
                logger.info("SUMMARY_SERVICE: acquired excel send lock (local mode)")
                return self._process_receipts(normalized)
    
    def _process_receipts(self, normalized: List) -> Dict[str, object]:
        """Process receipts and write to ledgers."""
        ordered = sorted(
            normalized,
            key=lambda r: (r.receipt_date is None, r.receipt_date or ""),
        )

        logger.info(f"SUMMARY_SERVICE: Processing {len(ordered)} receipts")
        
        results = []
        counts: Dict[str, int] = {"success": 0, "skipped": 0, "error": 0}

        for i, receipt in enumerate(ordered):
            logger.info(f"SUMMARY_SERVICE: Processing receipt {i+1}/{len(ordered)} - ID: {getattr(receipt, 'receipt_id', 'N/A')}")
            logger.info(f"SUMMARY_SERVICE: Receipt details - vendor={receipt.vendor_name}, location={receipt.business_location_id}, staff={receipt.staff_id}, invoice={receipt.invoice_number}")
            
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
        """Execute writer with isolation - single receipt failure doesn't block others."""
        try:
            return writer(receipt)
        except Exception as exc:  # defensive isolation
            # Propagate failure_type if the exception has one (e.g., LockTimeoutError)
            failure_type = getattr(exc, 'failure_type', None)
            return {
                "status": "error",
                "error": str(exc),
                "failure_type": failure_type.value if failure_type else "unknown"
            }

    @staticmethod
    def _tally(result: Dict[str, object], counts: Dict[str, int]) -> None:
        """Increment appropriate counter based on result status.
        
        Status conventions (Phase 11A-3):
        - 'written': Successfully written to ledger
        - 'skipped_*': Validation failure (missing field, etc.)
        - 'error': Write failure (Graph API, conflict, timeout, etc.)
        
        The result may also contain 'failure_type' for error classification.
        """
        status = (result or {}).get("status")
        if status == "written":
            counts["success"] += 1
        elif status and str(status).startswith("skipped"):
            counts["skipped"] += 1
        elif status == "error":
            counts["error"] += 1
