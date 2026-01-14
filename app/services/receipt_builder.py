"""ReceiptBuilder: central place to construct ExtractionResult objects.

Phase 2B – Step 2B.1 scaffolding:
- Keep mapping logic minimal for now.
- Do not refactor existing routes yet; this is additive-only.
- Methods accept raw OCR outputs/metadata and return a valid ExtractionResult with obvious fields populated.
- Detailed field mapping and merge logic remain TODO.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from datetime import datetime
from app.models.schema import ExtractionResult


def _safe_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _sanitize_iso_date(value: Any) -> Optional[str]:
    """Return ISO 8601 date (YYYY-MM-DD) or None if not parseable.

    Accepts common OCR artifacts like strings with non-digit separators or invalid year/month/day.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        candidate = value.strip()
        # Normalize full-width digits and separators
        trans = str.maketrans({
            "／": "/",
            "－": "-",
            "ー": "-",
            "―": "-",
            "―": "-",
            "　": " ",
        })
        candidate = candidate.translate(trans)
        # Replace slashes with hyphens
        candidate = candidate.replace("/", "-")
        # Trim any leading/trailing non-digit/non-hyphen chars
        while candidate and not candidate[0].isdigit():
            candidate = candidate[1:]
        while candidate and not candidate[-1].isdigit():
            candidate = candidate[:-1]
        # Heuristic fixes for obvious bad years (e.g., OCR “0569-74-03”)
        parts = candidate.split("-")
        if len(parts) >= 3:
            y, m, d = parts[0:3]
            if len(y) != 4 or not y.isdigit() or y.startswith("0"):
                candidate = None
            else:
                try:
                    return datetime.fromisoformat(f"{y}-{int(m):02d}-{int(d):02d}").date().isoformat()
                except Exception:
                    candidate = None
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except Exception:
            return None
    return None


class ReceiptBuilder:
    """Build ExtractionResult from various OCR sources.

    Public entrypoints are intentionally thin; they will be expanded with real
    mapping/merge logic in subsequent steps.
    """

    def build_from_standard_ocr(
        self,
        ocr_payload: Dict[str, Any],
        *,
        raw_text: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Construct an ExtractionResult from the standard OCR stack.

        Parameters
        ----------
        ocr_payload: dict
            Raw structured data from the standard OCR pipeline (e.g., merged fields, confidences).
        raw_text: str | None
            Full text content if available.
        processing_time_ms: int | None
            End-to-end processing time in milliseconds if available.
        metadata: dict | None
            Optional request/context metadata for future use.
        """
        payload: Dict[str, Any] = ocr_payload or {}

        # Prefer direct fields, then fall back to common nested containers used by the standard stack.
        structured: Dict[str, Any] = (
            payload.get("structured_data")
            or payload.get("entities")
            or {}
        )

        # Raw text preference: explicit arg > payload > structured blob.
        raw_text_value = raw_text or payload.get("raw_text") or structured.get("raw_text") or ""

        # Compute processing_time_ms if not provided, using standard timing keys (queue_wait + ocr + field_extractor in seconds).
        if processing_time_ms is None:
            timings = (payload.get("diagnostics") or {}).get("timings") or {}
            if timings:
                processing_time_ms = round(
                    (timings.get("queue_wait", 0.0)
                     + timings.get("ocr", 0.0)
                     + timings.get("field_extractor", 0.0))
                    * 1000
                )
            else:
                processing_time_ms = payload.get("processing_time_ms") or 0

        line_items = payload.get("line_items") or structured.get("line_items") or []
        fields_confidence = payload.get("fields_confidence") or structured.get("fields_confidence") or {}
        if isinstance(fields_confidence, dict):
            fields_confidence = {
                k: (v.get("confidence") if isinstance(v, dict) else v)
                for k, v in fields_confidence.items()
                if (not isinstance(v, dict)) or (isinstance(v.get("confidence"), (int, float))) or isinstance(v, (int, float))
            }
        if isinstance(fields_confidence, dict):
            fields_confidence = {
                k: (v.get("confidence") if isinstance(v, dict) else v)
                for k, v in fields_confidence.items()
                if (not isinstance(v, dict)) or (isinstance(v.get("confidence"), (int, float))) or isinstance(v, (int, float))
            }

        # TODO: Map vendor/date/currency/subtotal/tax/total/line_items from structured payload once contract is finalized.
        return ExtractionResult(
            receipt_id=uuid4(),
            vendor=payload.get("vendor") or structured.get("vendor"),
            date=_sanitize_iso_date(payload.get("date") or structured.get("date")),
            invoice_number=payload.get("invoice_number") or structured.get("invoice_number"),
            currency=payload.get("currency") or structured.get("currency"),
            subtotal=payload.get("subtotal") or structured.get("subtotal"),
            tax=payload.get("tax") or structured.get("tax"),
            total=payload.get("total") or structured.get("total"),
            line_items=line_items,
            raw_text=raw_text_value,
            fields_confidence=fields_confidence,
            verified=False,
            verification_issues=[],
            processing_time_ms=processing_time_ms,
            engine_used="standard",
            confidence_standard=payload.get("confidence_standard") or structured.get("confidence_standard"),
            confidence_docai=None,
            docai_raw_entities=None,
            docai_raw_fields=None,
            merged_fields=payload.get("entities") or structured.get("entities"),
            merge_strategy=payload.get("merge_strategy") or structured.get("merge_strategy") or "standard_only",
            overall_confidence=payload.get("confidence_standard") or structured.get("confidence_standard"),
            confidence_source="standard",
        )

    def build_from_document_ai(
        self,
        docai_payload: Dict[str, Any],
        *,
        raw_text: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Construct an ExtractionResult from Document AI output.

        Maps canonical fields from Document AI payloads; missing fields are allowed.
        TODO: tighten mapping once Document AI contract stabilizes (line items, currency hints, etc.).
        """
        payload: Dict[str, Any] = docai_payload or {}

        # Prefer direct fields, then nested docai structures.
        structured: Dict[str, Any] = (
            payload.get("structured_data")
            or payload.get("entities")
            or {}
        )

        # Raw text preference: explicit arg > payload > structured blob.
        raw_text_value = raw_text or payload.get("raw_text") or structured.get("raw_text") or ""

        # Compute processing_time_ms if not provided, using the same timing keys (seconds -> ms).
        if processing_time_ms is None:
            timings = (payload.get("diagnostics") or {}).get("timings") or {}
            if timings:
                processing_time_ms = round(
                    (timings.get("queue_wait", 0.0)
                     + timings.get("ocr", 0.0)
                     + timings.get("field_extractor", 0.0))
                    * 1000
                )
            else:
                processing_time_ms = payload.get("processing_time_ms") or 0

        line_items = payload.get("line_items") or structured.get("line_items") or []
        fields_confidence = payload.get("fields_confidence") or structured.get("fields_confidence") or {}
        if isinstance(fields_confidence, dict):
            fields_confidence = {
                k: (v.get("confidence") if isinstance(v, dict) else v)
                for k, v in fields_confidence.items()
                if (not isinstance(v, dict)) or (isinstance(v.get("confidence"), (int, float))) or isinstance(v, (int, float))
            }

        return ExtractionResult(
            receipt_id=uuid4(),
            vendor=payload.get("vendor") or structured.get("vendor"),
            date=_sanitize_iso_date(payload.get("date") or structured.get("date")),
            invoice_number=payload.get("invoice_number") or structured.get("invoice_number"),
            currency=payload.get("currency") or structured.get("currency"),
            subtotal=payload.get("subtotal") or structured.get("subtotal"),
            tax=payload.get("tax") or structured.get("tax"),
            total=payload.get("total") or structured.get("total"),
            line_items=line_items,
            raw_text=raw_text_value,
            fields_confidence=fields_confidence,
            verified=False,
            verification_issues=[],
            processing_time_ms=processing_time_ms,
            engine_used="document_ai",
            confidence_docai=payload.get("confidence_docai") or structured.get("confidence_docai"),
            confidence_standard=None,
            docai_raw_entities=_safe_dict(payload.get("docai_raw_entities") or structured.get("docai_raw_entities")),
            docai_raw_fields=_safe_dict(payload.get("docai_raw_fields") or structured.get("docai_raw_fields")),
            merged_fields=payload.get("entities") or structured.get("entities"),
            merge_strategy=payload.get("merge_strategy") or structured.get("merge_strategy") or "docai_over_standard",
            overall_confidence=payload.get("confidence_docai") or structured.get("confidence_docai"),
            confidence_source="document_ai",
        )

    def build_auto(
        self,
        standard_result: Optional[ExtractionResult],
        docai_result: Optional[ExtractionResult],
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Merge Document AI and Standard OCR results into one canonical ExtractionResult.

        Precedence is Document AI over Standard on a field-by-field basis; missing values are allowed.
        Merge logic is intentionally minimal and deterministic; no validation/normalization is performed here.
        """

        # Helper to prefer Document AI value when present (None means fallback to standard).
        def pick(docai_value: Any, standard_value: Any) -> Any:
            return docai_value if docai_value is not None else standard_value

        # Canonical fields with docai-over-standard precedence.
        vendor = pick(getattr(docai_result, "vendor", None), getattr(standard_result, "vendor", None))
        date = _sanitize_iso_date(pick(getattr(docai_result, "date", None), getattr(standard_result, "date", None)))
        invoice_number = pick(getattr(docai_result, "invoice_number", None), getattr(standard_result, "invoice_number", None))
        currency = pick(getattr(docai_result, "currency", None), getattr(standard_result, "currency", None))
        subtotal = pick(getattr(docai_result, "subtotal", None), getattr(standard_result, "subtotal", None))
        tax = pick(getattr(docai_result, "tax", None), getattr(standard_result, "tax", None))
        total = pick(getattr(docai_result, "total", None), getattr(standard_result, "total", None))

        # Line items: prefer docai list when populated, otherwise standard.
        docai_line_items = getattr(docai_result, "line_items", None)
        standard_line_items = getattr(standard_result, "line_items", None)
        line_items = docai_line_items if docai_line_items else (standard_line_items or [])

        # Raw text: prefer docai when available.
        raw_text = getattr(docai_result, "raw_text", None) or getattr(standard_result, "raw_text", "")

        # Processing time: prefer docai if present, else standard, else 0.
        processing_time_ms = (
            getattr(docai_result, "processing_time_ms", None)
            if docai_result and getattr(docai_result, "processing_time_ms", None) is not None
            else getattr(standard_result, "processing_time_ms", None)
        ) or 0

        # Confidence handling.
        confidence_docai = getattr(docai_result, "confidence_docai", None)
        confidence_standard = getattr(standard_result, "confidence_standard", None)
        overall_confidence = confidence_docai or confidence_standard
        confidence_source = "document_ai" if confidence_docai is not None else (
            "standard" if confidence_standard is not None else None
        )

        fields_confidence = (
            getattr(docai_result, "fields_confidence", None)
            or getattr(standard_result, "fields_confidence", None)
            or {}
        )

        merged_fields = {
            "vendor": vendor,
            "date": date,
            "invoice_number": invoice_number,
            "currency": currency,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "line_items": line_items,
            "raw_text": raw_text,
        }

        return ExtractionResult(
            receipt_id=uuid4(),
            vendor=vendor,
            date=date,
            invoice_number=invoice_number,
            currency=currency,
            subtotal=subtotal,
            tax=tax,
            total=total,
            line_items=line_items,
            raw_text=raw_text,
            fields_confidence=fields_confidence,
            verified=False,
            verification_issues=[],
            processing_time_ms=processing_time_ms,
            engine_used="document_ai+standard",
            confidence_docai=confidence_docai,
            confidence_standard=confidence_standard,
            docai_raw_entities=getattr(docai_result, "docai_raw_entities", None),
            docai_raw_fields=getattr(docai_result, "docai_raw_fields", None),
            merged_fields=merged_fields,
            merge_strategy="docai_over_standard",
            overall_confidence=overall_confidence,
            confidence_source=confidence_source,
        )


__all__ = ["ReceiptBuilder"]
