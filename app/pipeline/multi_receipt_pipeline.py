"""Minimal batch pipeline for Phase 2C (no Excel/persistence)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Sequence

from app.history.submission_history import SubmissionHistory
from app.ocr.multi_engine_ocr import MultiEngineOCR
from app.services.mapping_service import MappingService
from app.services.receipt_builder import ReceiptBuilder


class MultiReceiptPipeline:
    """Sequential multi-receipt processor (no Excel, no persistence)."""

    def __init__(self, engine: str, submission_history: SubmissionHistory):
        self.engine = engine
        self.submission_history = submission_history
        self.logger = logging.getLogger(__name__)
        self.ocr = MultiEngineOCR()
        self.mapping_service = MappingService()
        self.receipt_builder = ReceiptBuilder()

    def process_batch(self, batch_id: str, files: Sequence[str]):
        """Process a list of files and return mapped Receipts."""
        self.logger.info("Starting batch %s with %s files", batch_id, len(files))
        self.submission_history.update_batch_status(batch_id, 'processing')

        receipts = []
        for file_path in files:
            filename = Path(file_path).name
            self.submission_history.update_file_status(batch_id, filename, 'processing')
            receipt = self.process_single(file_path)
            receipts.append(receipt)
            self.submission_history.update_file_status(batch_id, filename, 'completed')

        self.submission_history.update_batch_status(batch_id, 'completed')
        self.logger.info("Completed batch %s", batch_id)
        return receipts

    def process_single(self, file_path: str):
        """Run OCR and mapping for a single file, returning Receipt or error payload."""
        self.logger.info("Processing file %s with engine %s", file_path, self.engine)
        try:
            image_bytes = Path(file_path).read_bytes()
        except Exception as exc:
            return {"status": "read_error", "file_path": file_path, "error": str(exc)}

        ocr_result = self.ocr.extract_structured(image_bytes, engine=self.engine)
        if not ocr_result.get('success'):
            return {"status": "ocr_failed", "file_path": file_path, "error": ocr_result.get('error')}

        # Build ExtractionResult instances
        standard = self.receipt_builder.build_from_standard_ocr(ocr_result, raw_text=ocr_result.get('raw_text'))
        docai_present = bool(ocr_result.get('docai_raw_entities') or ocr_result.get('docai_raw_fields'))
        docai = None
        if docai_present:
            docai = self.receipt_builder.build_from_document_ai(ocr_result, raw_text=ocr_result.get('raw_text'))

        if docai:
            extraction_result = self.receipt_builder.build_auto(standard, docai)
        else:
            extraction_result = standard

        receipt = self.mapping_service.map_to_receipt(extraction_result)
        return receipt
