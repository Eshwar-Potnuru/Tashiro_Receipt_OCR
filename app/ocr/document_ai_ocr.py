"""Document AI OCR scaffolding for Full Deployment Phase 1."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.ocr.document_ai_wrapper import (
    DocumentAIUnavailableError,
    DocumentAIWrapper,
    call_document_ai,
)

logger = logging.getLogger(__name__)


class DocumentAIOCREngine:
    """Template-driven Document AI engine with mock responses."""

    def __init__(
        self,
        wrapper: Optional[DocumentAIWrapper] = None,
        *,
        enable_mock: bool = False,
    ) -> None:
        self.wrapper = wrapper or DocumentAIWrapper()
        self.enable_mock = enable_mock

    def is_available(self) -> bool:
        """Report whether Document AI can be used in the current environment."""

        return self.enable_mock or self.wrapper.has_credentials()

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """Process an image stored on disk with Document AI (mock for now)."""

        logger.info(
            "Document AI engine invoked",
            extra={"engine": "document_ai", "file": Path(image_path).name},
        )

        if self.enable_mock:
            return self._build_mock_response(image_path)

        if not self.wrapper.has_credentials():
            raise DocumentAIUnavailableError(
                "Document AI credentials not configured. Enable mock mode or"
                " provide DOCUMENT_AI_* variables before calling process_image."
            )
        try:
            with open(image_path, "rb") as handle:
                file_bytes = handle.read()
            mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
            return call_document_ai(file_bytes, mime_type)
        except DocumentAIUnavailableError as exc:
            logger.warning("Document AI unavailable: %s", exc)
            return {}
        except Exception as exc:
            logger.error("Document AI processing failed: %s", exc)
            return {}

    def extract_structured_data(self, image_data: bytes) -> Dict[str, Any]:
        """Compatibility helper used by existing code paths."""

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as handle:
            handle.write(image_data)
            temp_path = handle.name
        try:
            return self.process_image(temp_path)
        except DocumentAIUnavailableError as exc:
            logger.warning("Document AI unavailable: %s", exc)
            return {}
        except Exception as exc:
            logger.error("Document AI processing failed: %s", exc)
            return {}
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.debug("Failed to remove temporary Document AI file", exc_info=True)

    def _build_mock_response(self, image_path: str) -> Dict[str, Any]:
        """Return a deterministic dummy payload used for unit tests."""

        sample_json_path = Path(__file__).with_suffix(".sample.json")
        if sample_json_path.exists():
            try:
                return json.loads(sample_json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in %s", sample_json_path)

        filename = Path(image_path).name
        logger.info("Using inline mock Document AI payload for %s", filename)
        return {
            "processor": "mock-processor",
            "text": "Sample Store\nTotal: ¥1,280",
            "entities": {
                "vendor_name": {"text": "Sample Store", "confidence": 0.94},
                "total_amount": {"text": "¥1,280", "confidence": 0.91},
                "receipt_date": {"text": "2024-11-05", "confidence": 0.89},
            },
            "fields": {
                "total": {"value": "1280", "confidence": 0.91},
                "date": {"value": "2024-11-05", "confidence": 0.89},
                "vendor": {"value": "Sample Store", "confidence": 0.94},
            },
            "line_items": [
                {"description": "Bento", "amount": "800"},
                {"description": "Tea", "amount": "480"},
            ],
            "confidence_scores": {
                "vendor_name": 0.94,
                "total_amount": 0.91,
                "receipt_date": 0.89,
            },
            "debug": {
                "source_file": filename,
                "mode": "mock",
            },
        }