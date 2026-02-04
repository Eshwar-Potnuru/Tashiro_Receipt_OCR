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
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.audit import AuditEventType
from app.models.draft import DraftReceipt, DraftStatus
from app.models.schema import Receipt
from app.repositories.audit_repository import AuditRepository
from app.repositories.draft_repository import DraftRepository
from app.services.audit_logger import AuditLogger
from app.services.config_service import ConfigService
from app.services.summary_service import SummaryService
import logging
import os

logger = logging.getLogger(__name__) 


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

    def save_draft(self, receipt: Receipt, image_ref: Optional[str] = None, image_data: Optional[str] = None, creator_user_id: Optional[str] = None) -> DraftReceipt:
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
            creator_user_id: Phase 5B.2 - Optional user ID who created this draft.
                            Set from authenticated request. NULL for unauthenticated.
        
        Returns:
            Created or updated DraftReceipt with status=DRAFT
        
        Phase 3 Guarantee:
            - SummaryService is NOT called
            - Excel writers are NOT invoked
            - Only DraftRepository is used
        
        Phase 4F Enhancement:
            - Prevents duplicate drafts for same receipt image
            - Updates existing draft if image_ref matches
        
        Phase 5B.2 Enhancement:
            - Tracks creator_user_id for ownership (no enforcement yet)
        
        Example:
            # First save
            draft1 = draft_service.save_draft(receipt, image_ref="queue-123")
            # draft1 is created
            
            # Second save with same image_ref
            draft2 = draft_service.save_draft(updated_receipt, image_ref="queue-123")
            # draft2.draft_id == draft1.draft_id (updated, not duplicated)
        """
        # Phase 5D-1.1: Defensive coercion - normalize creator_user_id to string
        if isinstance(creator_user_id, UUID):
            creator_user_id = str(creator_user_id)
        
        # Phase 4F.1: Check for existing draft with same image_ref
        if image_ref:
            existing_draft = self.repository.get_by_image_ref(image_ref)
            if existing_draft and existing_draft.status == DraftStatus.DRAFT:
                # Update existing draft instead of creating duplicate
                updated_draft = self.update_draft(existing_draft.draft_id, receipt)
                # Preserve/update image data for UI previews if provided
                if image_data:
                    updated_draft.image_ref = image_ref
                    updated_draft.image_data = image_data
                    try:
                        self.repository.save(updated_draft)
                    except Exception:
                        pass
                return updated_draft
        
        # No existing draft found, create new one
        draft = DraftReceipt(
            receipt=receipt,
            status=DraftStatus.DRAFT,
            image_ref=image_ref,
            image_data=image_data,
            creator_user_id=creator_user_id,  # Phase 5B.2: Track creator
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

    def create_drafts_from_images(
        self,
        images: List[Tuple[bytes, str]],  # List of (image_bytes, filename) tuples
        creator_user_id: Optional[str] = None,
        engine_preference: str = 'auto',
        receipt_builder: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Create multiple drafts from uploaded images (Phase 5C-2).
        
        Processes multiple receipt images in one operation, creating a separate
        draft for each successful OCR + extraction. Partial success is allowed:
        if one image fails, others are still processed.
        
        This operation does NOT trigger any Excel writes (save boundary only).
        
        Args:
            images: List of (image_bytes, filename) tuples to process
            creator_user_id: Optional user ID who is uploading (Phase 5B.2)
            engine_preference: OCR engine preference ('auto', 'standard', 'document_ai')
            receipt_builder: Optional ReceiptBuilder instance (injected for testing).
                            If None, will attempt to import and use ReceiptBuilder.
        
        Returns:
            Dictionary with batch results:
            {
                "total": int,  # Total images submitted
                "succeeded": int,  # Number of drafts created
                "failed": int,  # Number that failed
                "results": [  # Per-file results
                    {
                        "index": int,
                        "filename": str,
                        "status": "success" | "error",
                        "draft_id": str,  # Only if success
                        "error": str,  # Only if error
                        "error_code": str,  # Only if error (OCR_FAILED, EXTRACTION_FAILED, etc.)
                    }
                ]
            }
        
        Phase 3 Guarantee:
            - NO Excel writes
            - Only DraftRepository is used
            - Each draft created with status=DRAFT
        
        Phase 5C-2 Requirements:
            - Partial success: one failure doesn't block others
            - Each receipt gets unique image_ref (queue_id)
            - creator_user_id tracked for ownership
            - Validation respected (location/staff)
        
        Example:
            images = [
                (image1_bytes, "receipt1.jpg"),
                (image2_bytes, "receipt2.jpg"),
                (image3_bytes, "receipt3.jpg"),
            ]
            result = service.create_drafts_from_images(images, creator_user_id="user123")
            # result["succeeded"] == 2 (if one failed)
            # result["results"][0]["draft_id"] == "..."
            # result["results"][1]["error"] == "OCR extraction failed"
        """
        import base64
        from uuid import uuid4
        
        # Phase 5D-1.1: Defensive coercion - normalize creator_user_id to string
        if isinstance(creator_user_id, UUID):
            creator_user_id = str(creator_user_id)
        
        # Lazy import OCR dependencies (allows tests to inject mocks)
        try:
            from app.ocr.multi_engine_ocr import MultiEngineOCR
            ocr_engine = MultiEngineOCR()
        except Exception as e:
            return {
                "total": len(images),
                "succeeded": 0,
                "failed": len(images),
                "results": [
                    {
                        "index": i,
                        "filename": filename,
                        "status": "error",
                        "error": f"OCR service unavailable: {str(e)}",
                        "error_code": "OCR_SERVICE_UNAVAILABLE",
                    }
                    for i, (_, filename) in enumerate(images)
                ],
            }
        
        if receipt_builder is None:
            try:
                from app.services.receipt_builder import ReceiptBuilder
                receipt_builder = ReceiptBuilder()
            except Exception as e:
                return {
                    "total": len(images),
                    "succeeded": 0,
                    "failed": len(images),
                    "results": [
                        {
                            "index": i,
                            "filename": filename,
                            "status": "error",
                            "error": f"Receipt builder unavailable: {str(e)}",
                            "error_code": "BUILDER_SERVICE_UNAVAILABLE",
                        }
                        for i, (_, filename) in enumerate(images)
                    ],
                }
        
        total = len(images)
        succeeded = 0
        failed = 0
        results = []
        
        # If user explicitly requested Document AI only but it's not available, fail early with clear error
        engine_pref_lower = (engine_preference or 'auto').lower()
        if engine_pref_lower == 'document_ai' and not getattr(ocr_engine, 'engines_available', {}).get('document_ai', False):
            logger.error("Document AI requested but not available on server. Rejecting batch.")
            return {
                "total": total,
                "succeeded": 0,
                "failed": total,
                "results": [
                    {
                        "index": i,
                        "filename": filename,
                        "status": "error",
                        "error": "Document AI requested but not available on server",
                        "error_code": "DOC_AI_UNAVAILABLE",
                    }
                    for i, (_, filename) in enumerate(images)
                ],
            }

        # Process each image independently
        for index, (image_bytes, filename) in enumerate(images):
            try:
                # Generate unique queue_id for this image
                queue_id = str(uuid4())
                
                # Encode image as base64 for storage
                image_data_b64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # Run OCR extraction
                logger.info("Processing image index=%d filename=%s engine=%s size=%d", index, filename, engine_preference, len(image_bytes))
                try:
                    ocr_result = ocr_engine.extract_structured(image_bytes, engine=engine_preference)
                    if not ocr_result or not ocr_result.get("success"):
                        logger.warning("OCR result not successful for %s: %s", filename, ocr_result)
                        # Attach debug payload when enabled
                        if os.getenv('DEBUG_DRAFTS', '').lower() in {'1','true','yes','on'}:
                            results.append({
                                "index": index,
                                "filename": filename,
                                "status": "error",
                                "error": "OCR extraction failed: no success flag",
                                "error_code": "OCR_FAILED",
                                "debug_ocr": ocr_result,
                            })
                        else:
                            results.append({
                                "index": index,
                                "filename": filename,
                                "status": "error",
                                "error": "OCR extraction failed: no success flag",
                                "error_code": "OCR_FAILED",
                            })
                        failed += 1
                        continue
                except Exception as ocr_exc:
                    logger.exception("OCR extraction failed for %s (engine=%s): %s", filename, engine_preference, ocr_exc)
                    entry = {
                        "index": index,
                        "filename": filename,
                        "status": "error",
                        "error": f"OCR extraction failed: {str(ocr_exc)}",
                        "error_code": "OCR_FAILED",
                    }
                    if os.getenv('DEBUG_DRAFTS', '').lower() in {'1','true','yes','on'}:
                        entry['debug_ocr'] = getattr(ocr_result, 'structured_data', ocr_result) if ocr_result else None
                    results.append(entry)
                    failed += 1
                    continue
                
                # Build canonical Receipt from OCR result
                try:
                    # Choose builder strategy based on engine used
                    engine_used = (ocr_result.get('engine_used') or '').lower()
                    logger.info("OCR engine used for %s: %s", filename, engine_used)

                    if engine_used == 'document_ai':
                        # Document AI only
                        extraction_result = receipt_builder.build_from_document_ai(
                            ocr_result.get('structured_data') or ocr_result,
                            raw_text=ocr_result.get('raw_text', ''),
                            processing_time_ms=None,
                            metadata=None,
                        )
                    elif 'document_ai' in engine_used and 'standard' in engine_used:
                        # Hybrid result: build both and merge
                        standard_ex = receipt_builder.build_from_standard_ocr(
                            ocr_result,
                            raw_text=ocr_result.get('raw_text', ''),
                            processing_time_ms=None,
                            metadata=None,
                        )
                        docai_ex = receipt_builder.build_from_document_ai(
                            ocr_result.get('structured_data') or ocr_result,
                            raw_text=ocr_result.get('raw_text', ''),
                            processing_time_ms=None,
                            metadata=None,
                        )
                        extraction_result = receipt_builder.build_auto(standard_ex, docai_ex)
                    else:
                        # Default to standard pipeline
                        extraction_result = receipt_builder.build_from_standard_ocr(
                            ocr_result,
                            raw_text=ocr_result.get('raw_text', ''),
                            processing_time_ms=None,
                            metadata=None,
                        )

                    # Log key extracted fields for diagnostics
                    try:
                        logger.info(
                            "Extraction summary for %s: vendor=%s date=%s total=%s engine=%s",
                            filename,
                            getattr(extraction_result, 'vendor', None),
                            getattr(extraction_result, 'date', None),
                            getattr(extraction_result, 'total', None),
                            getattr(extraction_result, 'engine_used', None),
                        )
                    except Exception:
                        logger.debug("Could not log extraction summary for %s", filename)
                    
                    # Then convert to Receipt
                    receipt = receipt_builder.build_receipt(
                        extraction_result,
                        config_service=self.config_service,
                        validation_warnings=None,
                        validation_errors=None,
                    )
                except Exception as build_exc:
                    results.append({
                        "index": index,
                        "filename": filename,
                        "status": "error",
                        "error": f"Receipt extraction failed: {str(build_exc)}",
                        "error_code": "EXTRACTION_FAILED",
                    })
                    failed += 1
                    continue
                
                # Create draft (reuse existing save_draft logic)
                try:
                    draft = self.save_draft(
                        receipt=receipt,
                        image_ref=queue_id,
                        image_data=image_data_b64,
                        creator_user_id=creator_user_id,
                    )
                    
                    # Convert Decimal to float for JSON serialization
                    def decimal_to_float(value):
                        from decimal import Decimal
                        if isinstance(value, Decimal):
                            return float(value)
                        return value
                    
                    # Build extracted_data dict with fields from both Receipt and ExtractionResult
                    extracted_data = {
                        # Core Receipt fields
                        "vendor_name": receipt.vendor_name,
                        "receipt_date": receipt.receipt_date,
                        "invoice_number": receipt.invoice_number,
                        "total_amount": decimal_to_float(receipt.total_amount),
                        "tax_10_amount": decimal_to_float(receipt.tax_10_amount),
                        "tax_8_amount": decimal_to_float(receipt.tax_8_amount),
                        "memo": receipt.memo,
                        "business_location_id": receipt.business_location_id,
                        "staff_id": receipt.staff_id,
                        "ocr_engine": receipt.ocr_engine,
                        "ocr_confidence": receipt.ocr_confidence,
                    }
                    
                    # Add rich fields from ExtractionResult
                    if extraction_result:
                        extracted_data.update({
                            "expense_category": extraction_result.expense_category,
                            "expense_confidence": extraction_result.expense_confidence,
                            "tax_category": extraction_result.tax_classification,  # Map to frontend expected field name
                            "account_title": extraction_result.expense_category,  # Map to frontend expected field name
                            "subtotal": extraction_result.subtotal,
                            "tax_amount": extraction_result.tax,
                            "currency": extraction_result.currency,
                            "line_items_count": len(extraction_result.line_items) if extraction_result.line_items else 0,
                            "has_verification_issues": len(extraction_result.verification_issues) > 0 if extraction_result.verification_issues else False,
                        })
                    
                    success_entry = {
                        "index": index,
                        "filename": filename,
                        "status": "success",
                        "draft_id": str(draft.draft_id),
                        "image_ref": queue_id,  # ✅ ADDED: Return image_ref for frontend
                        "extracted_data": extracted_data,
                    }
                    # Attach OCR debug payload in debug mode for diagnosis
                    if os.getenv('DEBUG_DRAFTS', '').lower() in {'1','true','yes','on'}:
                        # Sanitize debug payload - only include essential information
                        debug_payload = {
                            "engine_used": ocr_result.get("engine_used"),
                            "success": ocr_result.get("success"),
                            "raw_text_preview": (ocr_result.get("raw_text", "") or "")[:500],  # First 500 chars only
                        }
                        
                        # Add structured data summary (not full payload)
                        structured = ocr_result.get("structured_data", {})
                        if structured:
                            entities = structured.get("entities", {})
                            debug_payload["extracted_fields"] = {
                                "vendor": entities.get("vendor", {}).get("text") if isinstance(entities.get("vendor"), dict) else None,
                                "date": entities.get("date", {}).get("text") if isinstance(entities.get("date"), dict) else None,
                                "total": entities.get("total", {}).get("text") if isinstance(entities.get("total"), dict) else None,
                                "invoice_number": entities.get("invoice_number", {}).get("text") if isinstance(entities.get("invoice_number"), dict) else None,
                            }
                            
                            # Add confidence scores summary
                            confidence_scores = structured.get("confidence_scores", {})
                            if confidence_scores:
                                debug_payload["confidence_summary"] = {
                                    k: round(v, 3) if isinstance(v, (int, float)) else v 
                                    for k, v in list(confidence_scores.items())[:5]  # Max 5 fields
                                }
                        
                        success_entry['debug_ocr'] = debug_payload

                    results.append(success_entry)
                    succeeded += 1
                    
                except Exception as save_exc:
                    results.append({
                        "index": index,
                        "filename": filename,
                        "status": "error",
                        "error": f"Draft save failed: {str(save_exc)}",
                        "error_code": "SAVE_FAILED",
                    })
                    failed += 1
                    continue
                    
            except Exception as outer_exc:
                # Catch-all for unexpected errors
                results.append({
                    "index": index,
                    "filename": filename,
                    "status": "error",
                    "error": f"Unexpected error: {str(outer_exc)}",
                    "error_code": "UNEXPECTED_ERROR",
                })
                failed += 1
        
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    def list_drafts(self, status: DraftStatus | None = None, user_id: str | None = None, include_image_data: bool = False) -> List[DraftReceipt]:
        """List all drafts, optionally filtered by status and user.
        
        Args:
            status: If provided, only return drafts with this status.
                   If None, return all drafts.
            user_id: If provided, only return drafts for this user.
                    If None, return drafts for all users (admin only).
            include_image_data: If True, includes base64 image_data for UI previews.
                               Use for admin/office views that need image display.
                               Default False to keep response payload small.
        
        Returns:
            List of DraftReceipt objects, most recent first
        
        Example:
            # Get all unsent drafts for a user
            drafts = draft_service.list_drafts(status=DraftStatus.DRAFT, user_id="user123")
            
            # Get all drafts for a user (including sent) WITH images
            all_drafts = draft_service.list_drafts(user_id="user123", include_image_data=True)
        """
        # Phase 5D-1.1: Defensive coercion - normalize user_id to string
        if isinstance(user_id, UUID):
            user_id = str(user_id)
        
        return self.repository.list_all(status=status, user_id=user_id, include_image_data=include_image_data)

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
                    "attempt_count": 0,  # Phase 5C-3
                    "last_send_attempt_at": None,  # Phase 5C-3
                    "last_send_error": None,  # Phase 5C-3
                })
                failed_count += 1
        
        # Separate DRAFT from SENT
        drafts_to_send = []
        for draft in drafts:
            if draft.status == DraftStatus.SENT:
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "already_sent",  # Phase 5C-3: distinct status
                    "error": f"Already sent at {draft.sent_at}",
                    "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                    "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                    "last_send_error": draft.last_send_error,  # Phase 5C-3
                })
                failed_count += 1
            elif draft.status == DraftStatus.DRAFT:
                drafts_to_send.append(draft)
            else:
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": f"Invalid status: {draft.status}",
                    "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                    "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                    "last_send_error": draft.last_send_error,  # Phase 5C-3
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
                # Phase 5C-1: Record validation error
                error_msg = f"Validation failed: {'; '.join(validation_errors)}"
                draft.last_send_error = error_msg[:500]
                draft.send_attempt_count += 1  # Count validation failures as attempts
                draft.last_send_attempt_at = datetime.utcnow()
                draft.updated_at = datetime.utcnow()
                # Status stays DRAFT
                try:
                    self.repository.save(draft)
                except Exception:
                    pass  # Best-effort
                
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "validation_failed",
                    "validation_errors": validation_errors,
                    "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                    "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                    "last_send_error": draft.last_send_error,  # Phase 5C-3
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
                            "attempt_count": draft.send_attempt_count,  # Phase 5C-1
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
        
        # Phase 5C-1: Record send attempt BEFORE calling Excel writers
        # This ensures we track attempts even if Excel write fails completely
        for draft in drafts_to_send:
            draft.send_attempt_count += 1
            draft.last_send_attempt_at = datetime.utcnow()
            draft.updated_at = datetime.utcnow()
            # Note: last_send_error will be set only if send fails
            # It will be cleared on success
            try:
                self.repository.save(draft)
            except Exception:
                # Best-effort: if we can't save attempt metadata, continue anyway
                # (business logic should not fail just because tracking failed)
                pass
        
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
                        "attempt_count": draft.send_attempt_count,  # Phase 5C-1
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
            # Phase 5C-1: Record error for each draft
            for draft in drafts_to_send:
                # Store last error (truncate to 500 chars for safety)
                error_msg = f"Excel write failed: {str(exc)}"
                draft.last_send_error = error_msg[:500]
                draft.updated_at = datetime.utcnow()
                # Status stays DRAFT (not SENT)
                try:
                    self.repository.save(draft)
                except Exception:
                    pass  # Best-effort
                
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": error_msg,
                    "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                    "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                    "last_send_error": draft.last_send_error,  # Phase 5C-3
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
        
        logger.info(f"SEND_DRAFTS: Processing {len(excel_results)} Excel results for {len(drafts_to_send)} drafts")
        logger.info(f"SEND_DRAFTS: summary_result = {summary_result}")
        
        for i, draft in enumerate(drafts_to_send):
            # Get corresponding Excel write result
            excel_result = excel_results[i] if i < len(excel_results) else {}
            
            logger.info(f"SEND_DRAFTS: Draft {draft.draft_id} - excel_result = {excel_result}")
            
            # Check if Excel write succeeded
            branch_status = excel_result.get("branch", {}).get("status")
            staff_status = excel_result.get("staff", {}).get("status")
            
            logger.info(f"SEND_DRAFTS: Draft {draft.draft_id} - branch_status={branch_status}, staff_status={staff_status}")
            
            # Phase 4C + 5C-1: Require BOTH outputs to succeed
            # Only mark as SENT if BOTH branch AND staff were written or already present.
            # If one fails, draft stays DRAFT and can be retried (without Excel writer changes).
            branch_success = branch_status in ["written", "skipped-no-change", "skipped_duplicate"]
            staff_success = staff_status in ["written", "skipped-no-change"]
            
            logger.info(f"SEND_DRAFTS: Draft {draft.draft_id} - branch_success={branch_success}, staff_success={staff_success}")
            
            success = branch_success and staff_success  # Both must succeed
            
            logger.info(f"SEND_DRAFTS: Draft {draft.draft_id} - final success={success}")
            
            if success:
                # Mark draft as SENT
                try:
                    draft.mark_as_sent()
                    # Phase 5C-1: Clear error on successful send
                    draft.last_send_error = None
                    draft.updated_at = datetime.utcnow()
                    self.repository.save(draft)
                    
                    results.append({
                        "draft_id": str(draft.draft_id),
                        "status": "sent",
                        "excel_result": excel_result,
                        "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                        "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                        "last_send_error": draft.last_send_error,  # Phase 5C-3 (should be None on success)
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
                                "attempt_count": draft.send_attempt_count,  # Phase 5C-1
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
                    # Phase 5C-1: Record error
                    error_msg = f"State update failed: {str(exc)}"
                    draft.last_send_error = error_msg[:500]
                    draft.updated_at = datetime.utcnow()
                    try:
                        self.repository.save(draft)
                    except Exception:
                        pass  # Best-effort
                    
                    results.append({
                        "draft_id": str(draft.draft_id),
                        "status": "error",
                        "error": error_msg,
                        "excel_result": excel_result,
                        "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                        "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                        "last_send_error": draft.last_send_error,  # Phase 5C-3
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
                # Phase 5C-1: Record error
                error_msg = "Excel write failed"
                error_details = excel_result.get("error", "")
                if error_details:
                    error_msg = f"{error_msg}: {error_details}"
                
                draft.last_send_error = error_msg[:500]
                draft.updated_at = datetime.utcnow()
                # Status stays DRAFT (not SENT)
                try:
                    self.repository.save(draft)
                except Exception:
                    pass  # Best-effort
                
                results.append({
                    "draft_id": str(draft.draft_id),
                    "status": "error",
                    "error": error_msg,
                    "excel_result": excel_result,
                    "attempt_count": draft.send_attempt_count,  # Phase 5C-3
                    "last_send_attempt_at": draft.last_send_attempt_at.isoformat() if draft.last_send_attempt_at else None,  # Phase 5C-3
                    "last_send_error": draft.last_send_error,  # Phase 5C-3
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
            List of canonical location IDs (e.g., ["Tokyo", "Osaka", "Kashima"])
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
