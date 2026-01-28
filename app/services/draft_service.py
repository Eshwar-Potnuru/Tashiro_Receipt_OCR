"""Phase 4B: Draft Service Layer

Business logic for draft receipt management, sitting in front of SummaryService.

Key Responsibilities:
- Validate state transitions
- Coordinate Save (no Excel) vs Send (Excel write)
- Enforce immutability rules
- Isolate Phase 3 boundary

Critical Rules:
- Save → creates/updates DRAFT (NO Excel write)
- Send → calls SummaryService.send_receipts() (YES Excel write)
- Send → only allowed for DRAFT status
- After send → drafts marked as SENT (immutable)
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.models.audit import AuditEventType
from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt
from app.repositories.audit_repository import AuditRepository
from app.repositories.draft_repository import DraftRepository
from app.services.audit_logger import AuditLogger
from app.services.config_service import ConfigService
from app.services.summary_service import SummaryService


class DraftService:
    """Service layer for draft receipt management.
    
    This service sits between the API layer and the persistence/Excel layers.
    It enforces Phase 4 workflow rules and coordinates between drafts and
    final submission.
    
    Architecture:
        API Layer (Phase 4B)
            ↓
        DraftService (this class) ← enforces state rules
            ↓
        DraftRepository ← persistence only
            ↓
        SummaryService ← Phase 3 boundary (Excel writes)
    
    State Management:
        - Save operations create/update drafts with status=DRAFT
        - Send operations transition DRAFT → SENT and trigger Excel writes
        - SENT drafts are immutable (cannot be edited or re-sent)
    
    Phase 3 Protection:
        - SummaryService is ONLY called during send operations
        - Save operations NEVER trigger Excel writes
        - Draft logic is completely isolated from Phase 3
    """

    def __init__(
        self,
        repository: DraftRepository | None = None,
        summary_service: SummaryService | None = None,
        config_service: ConfigService | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        """Initialize service with dependencies.
        
        Args:
            repository: DraftRepository for persistence. If None, creates default.
            summary_service: SummaryService for Excel writes. If None, creates default.
            config_service: ConfigService for location/staff validation. If None, creates default.
            audit_logger: AuditLogger for audit trail. If None, creates default.
        """
        self.repository = repository or DraftRepository()
        self.summary_service = summary_service or SummaryService()
        self.config_service = config_service or ConfigService()
        self.audit_logger = audit_logger or AuditLogger(AuditRepository())

    def save_draft(self, receipt: Receipt, image_ref: Optional[str] = None, image_data: Optional[str] = None) -> DraftReceipt:
        """Save a receipt as a draft (no Excel write).
        
        If image_ref is provided and a draft with that image_ref already exists,
        updates the existing draft instead of creating a new one (prevents duplicates).
        
        This operation does NOT trigger any Excel writes.
        
        Args:
            receipt: Canonical Receipt object to save as draft
            image_ref: Optional reference to source image (queue_id from /mobile/analyze).
                      Links draft to uploaded image for RDV UI verification.
                      Used for duplicate detection.
            image_data: Optional base64-encoded image data for Railway/cloud deployment.
                       Stores image inline to avoid ephemeral filesystem issues.
        
        Returns:
            Created or updated DraftReceipt with status=DRAFT
        
        Phase 3 Guarantee:
            - SummaryService is NOT called
            - Excel writers are NOT invoked
            - Only DraftRepository is used
        
        Phase 4F Enhancement:
            - Prevents duplicate drafts for same receipt image
            - Updates existing draft if image_ref matches
        
        Example:
            # First save
            draft1 = draft_service.save_draft(receipt, image_ref="queue-123")
            # draft1 is created
            
            # Second save with same image_ref
            draft2 = draft_service.save_draft(updated_receipt, image_ref="queue-123")
            # draft2.draft_id == draft1.draft_id (updated, not duplicated)
        """
        # Phase 4F.1: Check for existing draft with same image_ref
        if image_ref:
            existing_draft = self.repository.get_by_image_ref(image_ref)
            if existing_draft and existing_draft.status == DraftStatus.DRAFT:
                # Update existing draft instead of creating duplicate
                return self.update_draft(existing_draft.draft_id, receipt)
        
        # No existing draft found, create new one
        draft = DraftReceipt(
            receipt=receipt,
            status=DraftStatus.DRAFT,
            image_ref=image_ref,
            image_data=image_data,
        )
        
        saved_draft = self.repository.save(draft)
        
        # Phase 5A: Audit trail (best-effort, never blocks)
        try:
            self.audit_logger.log(
                event_type=AuditEventType.DRAFT_CREATED,
                draft_id=saved_draft.draft_id,
                data={
                    "image_ref": saved_draft.image_ref,
                    "vendor_name": saved_draft.receipt.vendor_name,
                    "receipt_date": saved_draft.receipt.receipt_date,
                    "total_amount": saved_draft.receipt.total_amount,
                    "business_location_id": saved_draft.receipt.business_location_id,
                    "staff_id": saved_draft.receipt.staff_id,
                },
            )
        except Exception:
            # Audit failures must not interrupt business operations
            pass
        
        return saved_draft

    def update_draft(self, draft_id: UUID, updated_receipt: Receipt) -> DraftReceipt:
        """Update an existing draft with new receipt data.
        
        Only allowed for drafts with status=DRAFT.
        SENT drafts are immutable and cannot be updated.
        
        Args:
            draft_id: UUID of the draft to update
            updated_receipt: New receipt data
        
        Returns:
            Updated DraftReceipt
        
        Raises:
            ValueError: If draft not found or already SENT
        
        Phase 3 Guarantee:
            - No Excel writes during update
            - Only draft state is modified
        """
        draft = self.repository.get_by_id(draft_id)
        
        if draft is None:
            raise ValueError(f"Draft not found: {draft_id}")
        
        # Use DraftReceipt's state validation
        draft.update_receipt_data(updated_receipt)
        
        updated_draft = self.repository.save(draft)
        
        # Phase 5A: Audit trail (best-effort, never blocks)
        try:
            self.audit_logger.log(
                event_type=AuditEventType.DRAFT_UPDATED,
                draft_id=updated_draft.draft_id,
                data={
                    "image_ref": updated_draft.image_ref,
                    "vendor_name": updated_draft.receipt.vendor_name,
                    "receipt_date": updated_draft.receipt.receipt_date,
                    "total_amount": updated_draft.receipt.total_amount,
                    "business_location_id": updated_draft.receipt.business_location_id,
                    "staff_id": updated_draft.receipt.staff_id,
                },
            )
        except Exception:
            # Audit failures must not interrupt business operations
            pass
        
        return updated_draft

    def list_drafts(self, status: DraftStatus | None = None) -> List[DraftReceipt]:
        """List all drafts, optionally filtered by status.
        
        Args:
            status: If provided, only return drafts with this status.
                   If None, return all drafts.
        
        Returns:
            List of DraftReceipt objects, most recent first
        
        Example:
            # Get all unsent drafts
            drafts = draft_service.list_drafts(status=DraftStatus.DRAFT)
            
            # Get all drafts (including sent)
            all_drafts = draft_service.list_drafts()
        """
        return self.repository.list_all(status=status)

    def get_draft(self, draft_id: UUID) -> DraftReceipt | None:
        """Retrieve a single draft by ID.
        
        Args:
            draft_id: UUID of the draft to retrieve
        
        Returns:
            DraftReceipt if found, None otherwise
        """
        return self.repository.get_by_id(draft_id)

    def delete_draft(self, draft_id: UUID) -> bool:
        """Delete a draft by ID.
        
        Can delete drafts in any state (DRAFT or SENT).
        
        Args:
            draft_id: UUID of the draft to delete
        
        Returns:
            True if deleted, False if not found
        
        Note:
            Deleting a SENT draft removes it from the draft store,
            but does NOT remove it from Excel (Excel is source of truth
            for sent receipts).
        """
        # Get draft before deletion for audit metadata
        draft = self.repository.get_by_id(draft_id)
        
        deleted = self.repository.delete(draft_id)
        
        # Phase 5A: Audit trail (best-effort even if draft not found)
        if deleted and draft:
            try:
                self.audit_logger.log(
                    event_type=AuditEventType.DRAFT_DELETED,
                    draft_id=draft_id,
                    data={
                        "image_ref": draft.image_ref,
                        "status_before_delete": draft.status.value,
                    },
                )
            except Exception:
                # Audit failures must not interrupt business operations
                pass
        
        return deleted

    def send_drafts(self, draft_ids: List[UUID]) -> Dict:
        """Send multiple drafts to Excel in bulk (DRAFT → SENT transition).
        
        This is the critical Phase 4 operation that:
        1. Loads drafts from repository
        2. Validates all are in DRAFT state
        3. Calls SummaryService.send_receipts() (Phase 3 boundary)
        4. Marks successfully sent drafts as SENT
        5. Handles partial failures gracefully
        
        Args:
            draft_ids: List of draft UUIDs to send
        
        Returns:
            Dictionary with:
                - total: Number of drafts requested
                - sent: Number successfully sent to Excel
                - failed: Number that failed
                - results: Per-draft results
        
        State Transitions:
            - Only DRAFT → SENT is allowed
            - SENT drafts are skipped with error message
            - Successfully sent drafts become immutable
        
        Phase 3 Integration:
            - SummaryService.send_receipts() is called with Receipt objects
            - Excel writes to Format 01 and Format 02
            - Per-receipt error isolation (Phase 3 guarantee)
        
        Error Handling:
            - Invalid draft IDs are reported as errors
            - Already-SENT drafts are reported as errors
            - Excel write failures don't prevent state updates of successful receipts
            - Partial success is allowed and reported clearly
        
        Example:
            result = draft_service.send_drafts([uuid1, uuid2, uuid3])
            # {
            #     "total": 3,
            #     "sent": 2,
            #     "failed": 1,
            #     "results": [
            #         {"draft_id": "...", "status": "sent"},
            #         {"draft_id": "...", "status": "sent"},
            #         {"draft_id": "...", "status": "error", "error": "..."}
            #     ]
            # }
        """
        # Load drafts from repository
        drafts = self.repository.get_by_ids(draft_ids)
        
        # Build lookup for error reporting
        drafts_by_id = {draft.draft_id: draft for draft in drafts}
        
        # Track results
        results = []
        sent_count = 0
        failed_count = 0
        
        # Validate all requested IDs exist
        for draft_id in draft_ids:
            if draft_id not in drafts_by_id:
                results.append({
                    "draft_id": str(draft_id),
                    "status": "error",
                    "error": "Draft not found",
                })
                failed_count += 1
        
        # Separate DRAFT from SENT
        drafts_to_send = []
        for draft in drafts:
            if draft.status == DraftStatus.SENT:
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": f"Already sent at {draft.sent_at}",
                })
                failed_count += 1
            elif draft.status == DraftStatus.DRAFT:
                drafts_to_send.append(draft)
            else:
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": f"Invalid status: {draft.status}",
                })
                failed_count += 1
        
        # If no valid drafts, return early
        if not drafts_to_send:
            return {
                "total": len(draft_ids),
                "sent": sent_count,
                "failed": failed_count,
                "results": results,
            }
        
        # ============================================================
        # PHASE 4C: READY-TO-SEND VALIDATION (before Excel writes)
        # ============================================================
        # Validate all drafts meet the READY-TO-SEND contract.
        # This prevents incomplete/invalid drafts from reaching Excel writers.
        # Validation happens HERE (service layer) instead of inside Excel writers
        # to eliminate silent skip behavior and provide clear user feedback.
        
        validated_drafts = []
        
        for draft in drafts_to_send:
            is_valid, validation_errors = self._validate_ready_to_send(draft)
            
            if not is_valid:
                # Validation failed - do NOT send this draft
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "validation_failed",
                    "validation_errors": validation_errors,
                })
                failed_count += 1
                
                # Phase 5A: Audit validation failure (best-effort)
                try:
                    self.audit_logger.log(
                        event_type=AuditEventType.SEND_VALIDATION_FAILED,
                        draft_id=draft.draft_id,
                        data={
                            "errors": validation_errors,
                            "vendor_name": draft.receipt.vendor_name,
                        },
                    )
                except Exception:
                    # Audit failures must not interrupt business operations
                    pass
            else:
                # Validation passed - draft is ready to send
                validated_drafts.append(draft)
        
        # If ALL drafts failed validation, return early (no Excel writes)
        if not validated_drafts:
            return {
                "total": len(draft_ids),
                "sent": sent_count,
                "failed": failed_count,
                "results": results,
            }
        
        # Only proceed with drafts that passed validation
        drafts_to_send = validated_drafts
        
        # Phase 5A: Audit SEND_ATTEMPTED for each draft being processed
        for draft in drafts_to_send:
            try:
                self.audit_logger.log(
                    event_type=AuditEventType.SEND_ATTEMPTED,
                    draft_id=draft.draft_id,
                    data={
                        "batch_size": len(drafts_to_send),
                        "vendor_name": draft.receipt.vendor_name,
                        "total_amount": draft.receipt.total_amount,
                    },
                )
            except Exception:
                # Audit failures must not interrupt business operations
                pass
        
        # Extract Receipt objects for SummaryService
        receipts = [draft.receipt for draft in drafts_to_send]
        
        # ============================================================
        # PHASE 3 BOUNDARY: Call SummaryService to write to Excel
        # ============================================================
        try:
            summary_result = self.summary_service.send_receipts(receipts)
        except Exception as exc:
            # If SummaryService fails completely, mark all as failed
            for draft in drafts_to_send:
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": f"Excel write failed: {str(exc)}",
                })
                failed_count += 1
            
            return {
                "total": len(draft_ids),
                "sent": sent_count,
                "failed": failed_count,
                "results": results,
            }
        
        # Process per-receipt results from SummaryService
        # summary_result["results"] contains per-receipt write status
        excel_results = summary_result.get("results", [])
        
        for i, draft in enumerate(drafts_to_send):
            # Get corresponding Excel write result
            excel_result = excel_results[i] if i < len(excel_results) else {}
            
            # Check if Excel write succeeded
            branch_status = excel_result.get("branch", {}).get("status")
            staff_status = excel_result.get("staff", {}).get("status")
            
            # Phase 4C: Remove silent skip behavior
            # Only treat as success if ACTUALLY written or no-change (duplicate).
            # "skipped-missing-data" is now impossible due to pre-send validation,
            # but we explicitly reject it here for defense-in-depth.
            success = (
                branch_status == "written" or
                branch_status == "skipped-no-change" or
                staff_status == "written" or
                staff_status == "skipped-no-change"
            ) and (
                branch_status != "skipped-missing-data" and
                staff_status != "skipped-missing-data"
            )
            
            if success:
                # Mark draft as SENT
                try:
                    draft.mark_as_sent()
                    self.repository.save(draft)
                    
                    results.append({
                        "draft_id": str(draft.draft_id),
                        "status": "sent",
                        "excel_result": excel_result,
                    })
                    sent_count += 1
                    
                    # Phase 5A: Audit successful send (best-effort)
                    try:
                        self.audit_logger.log(
                            event_type=AuditEventType.SEND_SUCCEEDED,
                            draft_id=draft.draft_id,
                            data={
                                "vendor_name": draft.receipt.vendor_name,
                                "total_amount": draft.receipt.total_amount,
                                "excel_result": {
                                    "branch_status": excel_result.get("branch", {}).get("status"),
                                    "branch_row": excel_result.get("branch", {}).get("row"),
                                    "staff_status": excel_result.get("staff", {}).get("status"),
                                    "staff_row": excel_result.get("staff", {}).get("row"),
                                },
                            },
                        )
                    except Exception:
                        # Audit failures must not interrupt business operations
                        pass
                except Exception as exc:
                    # State transition failed (unlikely)
                    results.append({
                        "draft_id": str(draft.draft_id),
                        "status": "error",
                        "error": f"State update failed: {str(exc)}",
                        "excel_result": excel_result,
                    })
                    failed_count += 1
                    
                    # Phase 5A: Audit send failure (status update stage, best-effort)
                    try:
                        self.audit_logger.log(
                            event_type=AuditEventType.SEND_FAILED,
                            draft_id=draft.draft_id,
                            data={
                                "error": str(exc),
                                "stage": "status_update",
                                "excel_result": excel_result,
                            },
                        )
                    except Exception:
                        # Audit failures must not interrupt business operations
                        pass
            else:
                # Excel write failed
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": "Excel write failed",
                    "excel_result": excel_result,
                })
                failed_count += 1
                
                # Phase 5A: Audit send failure (Excel write stage, best-effort)
                try:
                    self.audit_logger.log(
                        event_type=AuditEventType.SEND_FAILED,
                        draft_id=draft.draft_id,
                        data={
                            "error": "Excel write failed",
                            "stage": "excel_write",
                            "excel_result": excel_result,
                        },
                    )
                except Exception:
                    # Audit failures must not interrupt business operations
                    pass
        
        return {
            "total": len(draft_ids),
            "sent": sent_count,
            "failed": failed_count,
            "results": results,
        }
    
    # ============================================================
    # PHASE 4C: READY-TO-SEND Contract Enforcement
    # ============================================================
    
    def _validate_ready_to_send(
        self,
        draft: DraftReceipt
    ) -> Tuple[bool, List[str]]:
        """Validate that a draft meets all READY-TO-SEND contract requirements.
        
        This is the centralized enforcement point for the READY-TO-SEND contract.
        All validation rules are checked HERE before any Excel write occurs.
        This prevents incomplete/invalid drafts from being sent and eliminates
        silent skip behavior in Excel writers.
        
        Args:
            draft: DraftReceipt to validate
        
        Returns:
            Tuple of (is_valid, error_messages)
            - is_valid: True if all validations pass, False otherwise
            - error_messages: List of human-readable validation error strings
                             (empty if valid)
        
        Validation Rules (READY-TO-SEND Contract):
            A. Draft State:
                - status == DRAFT (not already SENT)
                - sent_at is None
            
            B. Business Identity:
                - business_location_id is present
                - business_location_id exists in locations config
                - staff_id is present
                - staff_id belongs to business_location_id
            
            C. Financial Integrity:
                - total_amount is present and > 0
                - tax_10_amount >= 0 (if present)
                - tax_8_amount >= 0 (if present)
            
            D. Date Integrity:
                - receipt_date is present
                - ISO format YYYY-MM-DD
                - Not in the future
                - Not earlier than year 2000
            
            E. Vendor Identity:
                - vendor_name is present and non-empty
        
        Example:
            is_valid, errors = self._validate_ready_to_send(draft)
            if not is_valid:
                # Errors: ["business_location_id is required", "total_amount must be positive"]
                return {"status": "validation_failed", "errors": errors}
        """
        errors = []
        receipt = draft.receipt
        
        # A. Draft State (defensive check - should already be validated)
        if draft.status != DraftStatus.DRAFT:
            errors.append(f"Draft status must be DRAFT, got {draft.status}")
        
        if draft.sent_at is not None:
            errors.append("Draft sent_at must be None (draft already sent)")
        
        # B. Business Identity
        # B1: business_location_id presence and validity
        if not receipt.business_location_id:
            errors.append("business_location_id is required")
        else:
            # Check if location exists in config
            valid_locations = self._get_valid_locations()
            if receipt.business_location_id not in valid_locations:
                errors.append(
                    f"business_location_id '{receipt.business_location_id}' is not valid. "
                    f"Valid locations: {', '.join(valid_locations)}"
                )
        
        # B2: staff_id presence and validity
        if not receipt.staff_id:
            errors.append("staff_id is required")
        elif receipt.business_location_id:
            # Check if staff belongs to location (only if location is valid)
            if not self._is_staff_valid_for_location(
                receipt.staff_id,
                receipt.business_location_id
            ):
                errors.append(
                    f"staff_id '{receipt.staff_id}' is not valid for "
                    f"location '{receipt.business_location_id}'"
                )
        
        # C. Financial Integrity
        # C1: total_amount must be present and positive
        if receipt.total_amount is None:
            errors.append("total_amount is required")
        elif receipt.total_amount <= 0:
            errors.append(f"total_amount must be positive, got {receipt.total_amount}")
        
        # C2: tax amounts must be non-negative (if present)
        if receipt.tax_10_amount is not None and receipt.tax_10_amount < 0:
            errors.append(f"tax_10_amount cannot be negative, got {receipt.tax_10_amount}")
        
        if receipt.tax_8_amount is not None and receipt.tax_8_amount < 0:
            errors.append(f"tax_8_amount cannot be negative, got {receipt.tax_8_amount}")
        
        # D. Date Integrity
        if not receipt.receipt_date:
            errors.append("receipt_date is required")
        else:
            # D1: ISO format validation (this should already be enforced by model validator,
            # but we check again for defense-in-depth)
            try:
                dt = datetime.fromisoformat(receipt.receipt_date)
                
                # D2: Not in the future
                if dt.date() > datetime.now().date():
                    errors.append(
                        f"receipt_date cannot be in the future, got {receipt.receipt_date}"
                    )
                
                # D3: Not earlier than year 2000 (sanity check)
                if dt.year < 2000:
                    errors.append(
                        f"receipt_date unreasonably old (pre-2000), got {receipt.receipt_date}"
                    )
            except (ValueError, TypeError) as e:
                errors.append(
                    f"receipt_date has invalid format (must be ISO YYYY-MM-DD), got {receipt.receipt_date}"
                )
        
        # E. Vendor Identity
        if not receipt.vendor_name or receipt.vendor_name.strip() == "":
            errors.append("vendor_name is required")
        
        # F. Image Reference (Phase 4C-3)
        # Enforce that draft has a link to the source image for RDV UI verification.
        # This prevents drafts created without proper image tracking from being sent.
        if not draft.image_ref or draft.image_ref.strip() == "":
            errors.append(
                "image_ref is required (source image reference missing). "
                "Draft must be linked to uploaded image."
            )
        
        # Return validation result
        is_valid = len(errors) == 0
        return (is_valid, errors)
    
    def _get_valid_locations(self) -> List[str]:
        """Get list of valid location IDs from config.
        
        Returns:
            List of canonical location IDs (e.g., ["aichi", "osaka", "keihin"])
        """
        return self.config_service.get_locations()
    
    def _is_staff_valid_for_location(
        self,
        staff_id: str,
        business_location_id: str
    ) -> bool:
        """Check if a staff_id is valid for a given business_location_id.
        
        Args:
            staff_id: Staff identifier to validate
            business_location_id: Location identifier to check against
        
        Returns:
            True if staff_id exists in the staff list for business_location_id,
            False otherwise
        """
        staff_list = self.config_service.get_staff_for_location(business_location_id)
        
        # Check if staff_id exists in the list
        for staff in staff_list:
            if staff.get("id") == staff_id:
                return True
        
        return False
