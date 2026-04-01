"""
HQ Transfer Writer Service (Phase 13)

This module provides the full HQ transfer orchestration service that:
1. Collects SENT receipts for an office-month
2. Writes each receipt to HQ Master Ledger via Graph API
3. Tracks batch progress and handles failures
4. Logs audit events for every operation
5. Updates draft HQ status

This service replaces the Phase 7A scaffold's stub behavior with actual Excel writes.

Usage:
    from app.services.hq_transfer_writer_service import HQTransferWriterService
    
    service = HQTransferWriterService()
    result = service.execute_month_end_transfer(
        office_id="Aichi",
        year=2026,
        month=3,
        user_id="admin123"
    )

Author: Phase 13 - Office Month-End Send to HQ
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from app.models.draft import DraftReceipt, DraftStatus
from app.models.audit import AuditEventType
from app.repositories.draft_repository import DraftRepository
from app.repositories.hq_transfer_repository import HQTransferRepository
from app.services.hq_master_ledger_writer import write_hq_row, write_hq_batch, HQWriteResult
from app.services.audit_logger import AuditLogger


_hq_transfer_lock = threading.Lock()
logger = logging.getLogger(__name__)


class HQTransferWriterService:
    """
    Full HQ transfer orchestration service with Graph API Excel writes.
    
    Key responsibilities:
    - Collect SENT receipts for transfer
    - Execute HQ Master Ledger writes
    - Track batch lifecycle (CREATED -> WRITING -> SUCCESS/FAILED)
    - Log audit events for compliance
    - Handle idempotent retry on existing SUCCESS batches
    """
    
    def __init__(
        self,
        hq_repository: Optional[HQTransferRepository] = None,
        draft_repository: Optional[DraftRepository] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.hq_repository = hq_repository or HQTransferRepository()
        self.draft_repository = draft_repository or DraftRepository()
        self.audit_logger = audit_logger or AuditLogger()
    
    def get_transfer_candidates(
        self,
        office_id: str,
        reporting_month: str
    ) -> List[DraftReceipt]:
        """
        Get SENT drafts eligible for HQ transfer.
        
        Rules:
        - Status must be SENT
        - business_location_id must match office_id
        - Exclude drafts already linked to SUCCESS batch for this scope
        
        Args:
            office_id: Business location identifier
            reporting_month: Format "YYYY-MM"
            
        Returns:
            List of DraftReceipt objects eligible for transfer
        """
        sent_drafts = self.draft_repository.list_all(status=DraftStatus.SENT, limit=None)
        
        candidates: List[DraftReceipt] = []
        for draft in sent_drafts:
            # Check office match
            receipt_location = getattr(draft.receipt, "business_location_id", None)
            if receipt_location != office_id:
                continue
            
            # Check if already transferred in a success batch
            existing_batch_id = getattr(draft, "hq_batch_id", None)
            if existing_batch_id and self.hq_repository.is_success_batch_for_scope(
                batch_id=str(existing_batch_id),
                office_id=office_id,
                reporting_month=reporting_month,
            ):
                continue
            
            candidates.append(draft)
        
        return candidates
    
    def _draft_to_receipt_data(self, draft: DraftReceipt) -> Dict[str, Any]:
        """Convert DraftReceipt to receipt data dict for HQ writer."""
        receipt = draft.receipt
        
        return {
            "draft_id": str(draft.draft_id),
            "business_location_id": receipt.business_location_id,
            "receipt_date": receipt.receipt_date,
            "vendor_name": receipt.vendor_name,
            "memo": getattr(receipt, "memo", None),
            "total_amount": receipt.total_amount,
            "invoice_number": getattr(receipt, "invoice_number", None),
            "tax_10_amount": getattr(receipt, "tax_10_amount", None),
            "tax_8_amount": getattr(receipt, "tax_8_amount", None),
            "account_title": getattr(receipt, "account_title", None),
            "staff_name": getattr(receipt, "staff_name", None),
        }
    
    def execute_month_end_transfer(
        self,
        office_id: str,
        year: int,
        month: int,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Execute month-end HQ transfer for an office.
        
        This is the main entry point for Phase 13 month-end operations.
        
        Process:
        1. Check for existing SUCCESS batch (idempotent return)
        2. Collect SENT candidates for office-month
        3. Create batch record -> CREATED
        4. Transition to WRITING state
        5. Write each receipt to HQ Master Ledger
        6. Transition to SUCCESS or FAILED
        7. Update draft HQ references
        
        Args:
            office_id: Business location identifier
            year: Transfer year
            month: Transfer month (1-12)
            user_id: User initiating the transfer
            
        Returns:
            dict with:
                - batch_id: UUID of the transfer batch
                - status: "success", "partial_failure", "failed", "idempotent"
                - receipt_count: Number of receipts processed
                - written_count: Number successfully written
                - failed_count: Number that failed
                - errors: List of error messages (if any)
                - reporting_month: "YYYY-MM" format
        """
        reporting_month = f"{year:04d}-{month:02d}"
        
        with _hq_transfer_lock:
            # IDEMPOTENCY CHECK: Return existing SUCCESS batch
            existing_success = self.hq_repository.get_latest_success_batch(
                office_id, reporting_month
            )
            if existing_success:
                existing_batch_id = str(existing_success["batch_id"])
                logger.info(
                    "hq_transfer_idempotent batch_id=%s office_id=%s reporting_month=%s",
                    existing_batch_id, office_id, reporting_month
                )
                return {
                    "batch_id": existing_batch_id,
                    "status": "idempotent",
                    "receipt_count": existing_success.get("receipt_count", 0),
                    "reporting_month": reporting_month,
                    "message": "Transfer already completed for this office-month"
                }
            
            # COLLECT CANDIDATES
            candidates = self.get_transfer_candidates(office_id, reporting_month)
            receipt_count = len(candidates)
            
            if receipt_count == 0:
                logger.info(
                    "hq_transfer_no_candidates office_id=%s reporting_month=%s",
                    office_id, reporting_month
                )
                return {
                    "batch_id": None,
                    "status": "no_candidates",
                    "receipt_count": 0,
                    "reporting_month": reporting_month,
                    "message": "No SENT receipts found for this office-month"
                }
            
            # CREATE BATCH
            batch_id = str(uuid4())
            self.hq_repository.create_batch(
                batch_id=batch_id,
                office_id=office_id,
                reporting_month=reporting_month,
                created_by_user_id=user_id,
            )
            
            # AUDIT: Transfer started
            self._log_audit(
                event_type=AuditEventType.HQ_TRANSFER_STARTED,
                actor=user_id,
                data={
                    "batch_id": batch_id,
                    "office_id": office_id,
                    "reporting_month": reporting_month,
                    "candidate_count": receipt_count,
                }
            )
            
            # TRANSITION TO WRITING
            self.hq_repository.mark_writing(batch_id)
            
            # EXECUTE WRITES
            written_count = 0
            failed_count = 0
            errors = []
            written_draft_ids = []
            
            for draft in candidates:
                receipt_data = self._draft_to_receipt_data(draft)
                
                result = write_hq_row(
                    receipt_data=receipt_data,
                    batch_id=batch_id,
                    year=year,
                    month=month,
                    user_id=user_id
                )
                
                if result.status == "written":
                    written_count += 1
                    written_draft_ids.append(str(draft.draft_id))
                    
                    # AUDIT: Row written
                    self._log_audit(
                        event_type=AuditEventType.HQ_ROW_WRITTEN,
                        actor=user_id,
                        draft_id=str(draft.draft_id),
                        data={
                            "batch_id": batch_id,
                            "office_id": office_id,
                            "sheet": result.sheet,
                            "row": result.row,
                        }
                    )
                else:
                    failed_count += 1
                    errors.append({
                        "draft_id": str(draft.draft_id),
                        "error": result.error or result.status
                    })
                    
                    # AUDIT: Row write failed
                    self._log_audit(
                        event_type=AuditEventType.HQ_ROW_WRITE_FAILED,
                        actor=user_id,
                        draft_id=str(draft.draft_id),
                        data={
                            "batch_id": batch_id,
                            "office_id": office_id,
                            "error": result.error or result.status,
                        }
                    )
            
            # DETERMINE FINAL STATUS
            if failed_count == 0:
                final_status = "success"
                self.hq_repository.mark_success(batch_id, receipt_count=written_count)
                
                # Update draft HQ references
                self.hq_repository.mark_drafts_transferred(
                    draft_ids=written_draft_ids,
                    batch_id=batch_id,
                )
                
                # AUDIT: Transfer completed
                self._log_audit(
                    event_type=AuditEventType.HQ_TRANSFER_COMPLETED,
                    actor=user_id,
                    data={
                        "batch_id": batch_id,
                        "office_id": office_id,
                        "reporting_month": reporting_month,
                        "written_count": written_count,
                    }
                )
                
            elif written_count == 0:
                final_status = "failed"
                error_summary = "; ".join(e["error"][:100] for e in errors[:5])
                self.hq_repository.mark_failed(batch_id, error_message=error_summary[:1000])
                
                # AUDIT: Transfer failed
                self._log_audit(
                    event_type=AuditEventType.HQ_TRANSFER_FAILED,
                    actor=user_id,
                    data={
                        "batch_id": batch_id,
                        "office_id": office_id,
                        "reporting_month": reporting_month,
                        "failed_count": failed_count,
                        "errors": errors[:10],
                    }
                )
                
            else:
                final_status = "partial_failure"
                # Mark as failed but include partial success info
                error_summary = f"Partial: {written_count}/{receipt_count} written. "
                error_summary += "; ".join(e["error"][:50] for e in errors[:3])
                self.hq_repository.mark_failed(batch_id, error_message=error_summary[:1000])
                
                # Still update successful drafts
                self.hq_repository.mark_drafts_transferred(
                    draft_ids=written_draft_ids,
                    batch_id=batch_id,
                )
                
                # AUDIT: Partial failure
                self._log_audit(
                    event_type=AuditEventType.HQ_TRANSFER_FAILED,
                    actor=user_id,
                    data={
                        "batch_id": batch_id,
                        "office_id": office_id,
                        "reporting_month": reporting_month,
                        "written_count": written_count,
                        "failed_count": failed_count,
                        "partial": True,
                        "errors": errors[:10],
                    }
                )
            
            logger.info(
                "hq_transfer_%s batch_id=%s office_id=%s reporting_month=%s "
                "written=%d failed=%d total=%d",
                final_status, batch_id, office_id, reporting_month,
                written_count, failed_count, receipt_count
            )
            
            return {
                "batch_id": batch_id,
                "status": final_status,
                "receipt_count": receipt_count,
                "written_count": written_count,
                "failed_count": failed_count,
                "errors": errors if errors else None,
                "reporting_month": reporting_month,
            }
    
    def _log_audit(
        self,
        event_type: AuditEventType,
        actor: str,
        draft_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an audit event for HQ transfer operations."""
        try:
            # Convert string draft_id to UUID if provided
            uuid_draft_id: Optional[UUID] = None
            if draft_id:
                try:
                    uuid_draft_id = UUID(draft_id)
                except ValueError:
                    pass  # Invalid UUID, skip
            
            self.audit_logger.log(
                event_type=event_type,
                actor=actor,
                draft_id=uuid_draft_id,
                data=data or {}
            )
        except Exception as e:
            # Audit logging should not interrupt transfer flow
            logger.warning(f"Failed to log audit event: {e}")
    
    def get_transfer_status(
        self,
        office_id: str,
        reporting_month: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the current transfer status for an office-month.
        
        Args:
            office_id: Business location identifier
            reporting_month: Format "YYYY-MM"
            
        Returns:
            Latest batch record or None if no transfers attempted
        """
        return self.hq_repository.get_latest_batch(office_id, reporting_month)
    
    def get_pending_offices(self, reporting_month: str) -> List[Dict[str, Any]]:
        """
        Get offices that have SENT receipts but no SUCCESS transfer for the month.
        
        Args:
            reporting_month: Format "YYYY-MM"
            
        Returns:
            List of dicts with office_id and pending_count
        """
        sent_drafts = self.draft_repository.list_all(status=DraftStatus.SENT, limit=None)
        
        # Group by office
        office_counts: Dict[str, int] = {}
        for draft in sent_drafts:
            location = getattr(draft.receipt, "business_location_id", None)
            if location:
                # Check if already has success batch
                existing = self.hq_repository.get_latest_success_batch(
                    location, reporting_month
                )
                if not existing:
                    office_counts[location] = office_counts.get(location, 0) + 1
        
        return [
            {"office_id": office_id, "pending_count": count}
            for office_id, count in office_counts.items()
            if count > 0
        ]
