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
<<<<<<< HEAD
    
    def log_config(self) -> None:
        """Log Document AI configuration for debugging."""
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        logger.info("=" * 60)
        logger.info("Document AI Configuration:")
        logger.info(f"  Project ID: {self.project_id}")
        logger.info(f"  Location: {self.location}")
        logger.info(f"  Processor ID: {self.processor_id}")
        logger.info(f"  Processor Name: {self.processor_name}")
        logger.info(f"  API Endpoint: {self.location}-documentai.googleapis.com")
        if creds_path:
            logger.info(f"  Credentials: {creds_path}")
            logger.info(f"  Credentials exist: {Path(creds_path).exists() if creds_path else False}")
        else:
            logger.warning("  Credentials: NOT SET (GOOGLE_APPLICATION_CREDENTIALS missing)")
        logger.info("=" * 60)
=======
>>>>>>> 9e2daf15213dd71eff959806c399d94fb9510fdd

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
<<<<<<< HEAD

        # Prefer explicit env if already set
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return True

        base_dir = Path(__file__).resolve().parents[2]
        # Shared service account key for both Vision and DocAI
        fallback_key = base_dir / "config" / "aim-tashiro-poc-09a7f137eb05.json"
        legacy_key = base_dir / "config" / "google_vision_key.json"

        for candidate in (fallback_key, legacy_key):
            if candidate.exists():
                # Set env so downstream Google clients can pick it up.
                os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(candidate))
                return True

        return False
=======
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return True
        credentials_file = Path("config/google_vision_key.json")
        return credentials_file.exists()
>>>>>>> 9e2daf15213dd71eff959806c399d94fb9510fdd

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
<<<<<<< HEAD
    config.log_config()
    
    if not config.processor_name:
        logger.error("Document AI processor configuration missing")
        logger.error("Required: DOCUMENT_AI_PROJECT_ID and DOCUMENT_AI_PROCESSOR_ID")
=======
    if not config.processor_name:
        logger.warning("Document AI processor configuration missing (PROJECT_ID/PROCESSOR_ID)")
>>>>>>> 9e2daf15213dd71eff959806c399d94fb9510fdd
        raise DocumentAIUnavailableError("Document AI processor configuration missing")

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
<<<<<<< HEAD
        logger.error("GOOGLE_APPLICATION_CREDENTIALS not set in environment")
        logger.error("Expected path: config/aim-tashiro-poc-09a7f137eb05.json")
        raise DocumentAIUnavailableError("Document AI credentials not configured")
    
    if not Path(credentials_path).exists():
        logger.error(f"Credentials file not found: {credentials_path}")
        raise DocumentAIUnavailableError(f"Credentials file not found: {credentials_path}")
=======
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set")
        raise DocumentAIUnavailableError("Document AI credentials not configured")
>>>>>>> 9e2daf15213dd71eff959806c399d94fb9510fdd

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
<<<<<<< HEAD
        logger.error("Document AI processing failed: %s", exc)
        # Check for permission errors
        error_str = str(exc)
        if "401" in error_str or "authentication" in error_str.lower():
            logger.error("Authentication failed - check service account credentials")
            logger.error("Service account: aim-vision-api-dev@aim-tashiro-poc.iam.gserviceaccount.com")
        if "403" in error_str or "permission" in error_str.lower():
            logger.error("Permission denied - service account may be missing IAM roles")
            logger.error("Required roles: roles/documentai.apiUser or roles/documentai.editor")
=======
        logger.warning("Document AI processing failed: %s", exc)
>>>>>>> 9e2daf15213dd71eff959806c399d94fb9510fdd
        raise DocumentAIUnavailableError("Document AI call failed") from exc
