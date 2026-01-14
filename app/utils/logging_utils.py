"""Lightweight JSON logging utilities for OCR instrumentation."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "logs"
LOG_FILE = LOG_DIR / "ocr.log"
SENSITIVE_KEYS = {"raw_text", "raw_image", "image_data", "text_dump"}


def log_ocr_event(event: Dict[str, Any]) -> None:
	"""Persist a structured OCR event without leaking sensitive payloads."""

	payload = {
		"timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
	}
	for key, value in event.items():
		if key is None:
			continue
		normalized = str(key)
		if normalized.lower() in SENSITIVE_KEYS:
			continue
		payload[normalized] = value

	try:
		LOG_DIR.mkdir(parents=True, exist_ok=True)
		with LOG_FILE.open("a", encoding="utf-8") as handle:
			json.dump(payload, handle, ensure_ascii=False)
			handle.write("\n")
	except Exception as exc:  # pragma: no cover - logging must never break pipeline
		logger.debug("Failed to write OCR log: %s", exc, exc_info=True)


def log_batch_event(event: Dict[str, Any]) -> None:
	"""Record high-level batch lifecycle events."""

	payload = {"event_type": "batch"}
	payload.update(event)
	log_ocr_event(payload)


def log_batch_file_event(event: Dict[str, Any]) -> None:
	"""Record per-file status changes within a batch."""

	payload = {"event_type": "batch_file"}
	payload.update(event)
	log_ocr_event(payload)
