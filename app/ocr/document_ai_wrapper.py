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

    project_id: Optional[str] = None
    location: str = "us"
    processor_id: Optional[str] = None
    api_key: Optional[str] = None
    endpoint: str = "https://us-documentai.googleapis.com/v1"
    
    def __post_init__(self):
        """Load configuration from environment variables."""
        if self.project_id is None:
            self.project_id = os.getenv("DOCUMENT_AI_PROJECT_ID")
        if self.location == "us":  # Only override if default
            self.location = os.getenv("DOCUMENT_AI_LOCATION", "us")
        if self.processor_id is None:
            self.processor_id = os.getenv("DOCUMENT_AI_PROCESSOR_ID")
        if self.api_key is None:
            self.api_key = os.getenv("DOCUMENT_AI_API_KEY")
        if self.endpoint == "https://us-documentai.googleapis.com/v1":  # Only override if default
            self.endpoint = os.getenv("DOCUMENT_AI_ENDPOINT", "https://us-documentai.googleapis.com/v1")
    
    def log_config(self) -> None:
        """Log safe Document AI configuration details (debug-level only)."""
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        # Keep details debug-only and avoid printing credential file paths to logs.
        logger.debug(
            "Document AI Configuration: project_id=%s location=%s processor_id=%s processor_name=%s",
            self.project_id,
            self.location,
            self.processor_id,
            self.processor_name,
        )
        logger.debug("GOOGLE_APPLICATION_CREDENTIALS set: %s", bool(creds_path))

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

        # Prefer explicit env if already set
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return True

        base_dir = Path(__file__).resolve().parents[2]
        # Shared service account key for both Vision and DocAI
        fallback_key = base_dir / "config" / "aim-tashiro-poc-dec6e8e0cdb7.json"
        legacy_key = base_dir / "config" / "google_vision_key.json"

        for candidate in (fallback_key, legacy_key):
            if candidate.exists():
                # Set env so downstream Google clients can pick it up.
                os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(candidate))
                return True

        return False

    def process_document(self, image_path: str) -> Dict[str, object]:
        """Process an image file using Document AI.

        Accepts a local file path, reads the file, and returns the raw Document AI
        payload as a plain dictionary. Raises DocumentAIUnavailableError when
        configuration, credentials, or the SDK are not available so callers can
        fall back to alternate OCR engines.
        """
        if not self.has_credentials():
            raise DocumentAIUnavailableError(
                "Document AI credentials not configured. Set DOCUMENT_AI_* env vars "
                "or GOOGLE_APPLICATION_CREDENTIALS to a valid service account JSON file."
            )

        try:
            path = Path(image_path)
            file_bytes = path.read_bytes()
        except Exception as exc:
            logger.error("Failed to read image file '%s': %s", image_path, exc)
            raise DocumentAIUnavailableError(f"Could not read image file: {image_path}") from exc

        # Determine MIME type for the raw document; default to octet-stream
        import mimetypes

        mime_type, _ = mimetypes.guess_type(path.name)
        mime_type = mime_type or "application/octet-stream"

        # Delegate to the helper which handles SDK/credentials checks and the API call
        return call_document_ai(file_bytes, mime_type) 


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
        logger.debug("Document AI SDK import failed: %s", exc)
        raise DocumentAIUnavailableError("google-cloud-documentai is not installed") from exc

    config = DocumentAIConfig()
    # Intentionally do not log configuration here to avoid leaking credential paths or
    # other sensitive information. Use debug logging in development if needed.
    
    if not config.processor_name:
        logger.error("Document AI processor configuration missing")
        logger.error("Required: DOCUMENT_AI_PROJECT_ID and DOCUMENT_AI_PROCESSOR_ID")
        raise DocumentAIUnavailableError("Document AI processor configuration missing")

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        logger.error("GOOGLE_APPLICATION_CREDENTIALS not set in environment")
        raise DocumentAIUnavailableError(
            "Document AI credentials not configured. Set GOOGLE_APPLICATION_CREDENTIALS "
            "to a service account JSON file with Document AI access."
        )
    
    if not Path(credentials_path).exists():
        logger.error(f"Credentials file not found: {credentials_path}")
        raise DocumentAIUnavailableError(f"Credentials file not found: {credentials_path}")

    # Determine API endpoint from configuration; prefer explicit endpoint
    from urllib.parse import urlparse
    parsed = urlparse(config.endpoint)
    api_endpoint = parsed.netloc or config.endpoint
    # client expects host like 'us-documentai.googleapis.com'

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
        logger.error("Document AI processing failed: %s", exc)
        # Check for permission errors
        error_str = str(exc)
        if "401" in error_str or "authentication" in error_str.lower():
            logger.error("Authentication failed - check service account credentials")
        if "403" in error_str or "permission" in error_str.lower():
            logger.error("Permission denied - service account may be missing IAM roles")
            logger.error("Required roles: roles/documentai.apiUser or roles/documentai.editor")
        raise DocumentAIUnavailableError("Document AI call failed") from exc
