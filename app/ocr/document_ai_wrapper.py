"""Lightweight wrapper scaffolding for future Google Document AI integration.

This module intentionally avoids importing the real Document AI client. It only
stores configuration and exposes placeholders so that we can connect the real
API later without refactoring business logic.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DocumentAIUnavailableError(RuntimeError):
    """Raised when a Document AI request cannot be performed."""


@dataclass
class DocumentAIConfig:
    """Runtime configuration for Document AI requests."""

    project_id: Optional[str] = os.getenv("DOCUMENT_AI_PROJECT_ID")
    location: str = os.getenv("DOCUMENT_AI_LOCATION", "us")
    processor_id: Optional[str] = os.getenv("DOCUMENT_AI_PROCESSOR_ID")
    api_key: Optional[str] = os.getenv("DOCUMENT_AI_API_KEY")
    endpoint: str = os.getenv(
        "DOCUMENT_AI_ENDPOINT",
        "https://us-documentai.googleapis.com/v1"
    )

    @property
    def processor_name(self) -> Optional[str]:
        if not (self.project_id and self.processor_id):
            return None
        return f"projects/{self.project_id}/locations/{self.location}/processors/{self.processor_id}"


class DocumentAIWrapper:
    """Placeholder wrapper around the future Document AI HTTP/gRPC client."""

    def __init__(self, config: Optional[DocumentAIConfig] = None) -> None:
        self.config = config or DocumentAIConfig()

    def has_credentials(self) -> bool:
        """Return True if we have enough information to call the real API."""

        if self.config.api_key:
            return True
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return True
        credentials_file = Path("config/google_vision_key.json")
        return credentials_file.exists()

    def process_document(self, image_path: str) -> Dict[str, object]:
        """Placeholder for the real Document AI call.

        TODO: Replace this implementation with a call to Document AI once we
        obtain credentials. For now we raise a descriptive error so the caller
        can decide whether to fall back to mock data.
        """

        raise DocumentAIUnavailableError(
            "Document AI credentials not configured. Configure DOCUMENT_AI_*"
            " environment variables or GOOGLE_APPLICATION_CREDENTIALS before"
            " enabling live requests."
        )


def call_document_ai(file_bytes: bytes, mime_type: str) -> Dict[str, object]:
    """Call Google Document AI and return the raw document payload.

    This function deliberately avoids any mapping/normalization. It raises
    DocumentAIUnavailableError for configuration or SDK problems so callers can
    fall back gracefully.
    """

    try:  # Import inside to avoid hard failure when SDK is missing
        from google.cloud import documentai  # type: ignore
        from google.protobuf.json_format import MessageToDict  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Document AI SDK not available: %s", exc)
        raise DocumentAIUnavailableError("google-cloud-documentai is not installed") from exc

    config = DocumentAIConfig()
    if not config.processor_name:
        logger.warning("Document AI processor configuration missing (PROJECT_ID/PROCESSOR_ID)")
        raise DocumentAIUnavailableError("Document AI processor configuration missing")

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set")
        raise DocumentAIUnavailableError("Document AI credentials not configured")

    api_endpoint = f"{config.location}-documentai.googleapis.com"

    try:
        client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": api_endpoint}
        )

        raw_doc = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
        request = documentai.ProcessRequest(
            name=config.processor_name,
            raw_document=raw_doc,
        )

        response = client.process_document(request=request)
        if not response.document:
            return {}

        # Convert protobuf Document to a plain dict for downstream mapping
        return MessageToDict(response.document._pb, preserving_proto_field_name=True)

    except Exception as exc:  # pragma: no cover - network/SDK failures
        logger.warning("Document AI processing failed: %s", exc)
        raise DocumentAIUnavailableError("Document AI call failed") from exc
