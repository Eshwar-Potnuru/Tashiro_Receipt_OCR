"""Utility helpers for mapping Document AI payloads to internal schema.

TODO: Align entity mapping outputs with the upcoming mapping controller interfaces.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

logger = logging.getLogger(__name__)

DOCUMENT_AI_ENTITY_MAP: Mapping[str, str] = {
    "total_amount": "total",
    "net_amount": "total",
    "total": "total",
    "subtotal_amount": "subtotal",
    "subtotal": "subtotal",
    "tax_amount": "tax",
    "vat_amount": "tax",
    "tax": "tax",
    "supplier_name": "vendor",
    "vendor_name": "vendor",
    "merchant_name": "vendor",
    "store_name": "vendor",
    "receipt_date": "date",
    "invoice_date": "date",
    "date": "date",
    "receipt_id": "invoice_number",
    "invoice_id": "invoice_number",
    "document_id": "invoice_number",
}

LINE_ITEM_FIELDS = {"description", "amount", "qty", "quantity", "unit_price", "price"}


@dataclass
class StructuredDocument:
    raw_text: str = ""
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    totals: Dict[str, Any] = field(default_factory=dict)
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "entities": self.entities,
            "confidence_scores": self.confidence_scores,
            "totals": self.totals,
            "line_items": self.line_items,
            "metadata": self.metadata,
        }


def map_document_ai_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert a raw Document AI response (or mock) to the internal format."""

    document = StructuredDocument()

    document.raw_text = _extract_raw_text(payload)
    entities, confidences = _normalize_entities(payload.get("entities"))

    # Merge fallback "fields" dicts if provided by mock implementations
    fallback_fields = payload.get("fields") or {}
    for key, value in fallback_fields.items():
        canonical_key = DOCUMENT_AI_ENTITY_MAP.get(key, key)
        if canonical_key not in entities:
            entities[canonical_key] = _wrap_value(value)
            confidences.setdefault(canonical_key, _coerce_confidence(value))

    document.entities = entities
    document.confidence_scores = confidences
    document.totals = _extract_totals(payload, entities)
    document.line_items = _extract_line_items(payload)
    document.metadata = {
        "source": payload.get("processor", "document_ai"),
        "mode": payload.get("debug", {}).get("mode", "live"),
        "raw_metadata": {
            key: payload.get(key)
            for key in ("processor", "revisions", "pages")
            if payload.get(key) is not None
        },
    }
    if payload.get("fields") is not None:
        document.metadata["raw_fields"] = payload.get("fields")
    if payload.get("entities") is not None:
        document.metadata["raw_entities"] = payload.get("entities")

    return document.asdict()


def validate_structured_payload(structured: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Ensure downstream consumers receive all required keys."""

    structured.setdefault("raw_text", "")
    structured.setdefault("entities", {})
    structured.setdefault("confidence_scores", {})
    structured.setdefault("totals", {})
    structured.setdefault("line_items", [])

    missing = [key for key in ("vendor", "date", "total") if key not in structured["entities"]]
    if missing:
        logger.info("Document AI payload missing canonical entities: %s", ", ".join(missing))

    return structured


def _extract_raw_text(payload: Mapping[str, Any]) -> str:
    for key in ("text", "raw_text", "full_text"):
        text_value = payload.get(key)
        if isinstance(text_value, str) and text_value.strip():
            return text_value
    return ""


def _normalize_entities(raw_entities: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, float]]:
    entities: Dict[str, Dict[str, Any]] = {}
    confidences: Dict[str, float] = {}

    if isinstance(raw_entities, Mapping):
        for key, value in raw_entities.items():
            entities[key] = _wrap_value(value)
            confidences[key] = _coerce_confidence(value)
        return entities, confidences

    if isinstance(raw_entities, Iterable):
        for entry in raw_entities:
            if not isinstance(entry, Mapping):
                continue
            entity_type = entry.get("type") or entry.get("type_") or entry.get("field_type")
            if not entity_type:
                continue
            text_value = _extract_text(entry)
            canonical = DOCUMENT_AI_ENTITY_MAP.get(entity_type, entity_type)
            entities[canonical] = {"text": text_value, "raw": entry}
            confidences[canonical] = float(entry.get("confidence", 0.0))
        return entities, confidences

    return entities, confidences


def _wrap_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        if "text" in value:
            return {"text": value.get("text"), "confidence": value.get("confidence")}
        if "value" in value:
            return {"text": value.get("value"), "confidence": value.get("confidence")}
    return {"text": str(value)}


def _coerce_confidence(value: Any) -> float:
    if isinstance(value, Mapping):
        raw = value.get("confidence")
        if isinstance(raw, (int, float)):
            return max(0.0, min(float(raw), 1.0))
    return 0.5


def _extract_text(entry: Mapping[str, Any]) -> str:
    for key in ("text", "mention_text", "value", "content"):
        text_value = entry.get(key)
        if isinstance(text_value, str) and text_value.strip():
            return text_value
    text_anchor = entry.get("text_anchor") if isinstance(entry, Mapping) else None
    if isinstance(text_anchor, Mapping):
        content = text_anchor.get("content")
        if isinstance(content, str):
            return content
    return ""


def _extract_totals(payload: Mapping[str, Any], entities: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, Any] = {}
    candidate_sources = [payload.get("totals"), payload.get("summary"), payload.get("total"), payload.get("amounts")]

    for source in candidate_sources:
        if isinstance(source, Mapping):
            for key, value in source.items():
                canonical = DOCUMENT_AI_ENTITY_MAP.get(key, key)
                if canonical.startswith("total") and value:
                    totals["total"] = _clean_amount(str(value))
                if canonical == "tax":
                    totals["tax"] = _clean_amount(str(value))
                if canonical == "subtotal":
                    totals["subtotal"] = _clean_amount(str(value))

    # Fall back to entities if totals dict is empty
    if "total" not in totals:
        entity = entities.get("total") or entities.get("total_amount")
        if entity:
            totals["total"] = _clean_amount(str(entity.get("text")))
    if "tax" not in totals and "tax" in entities:
        totals["tax"] = _clean_amount(str(entities["tax"].get("text")))
    if "subtotal" not in totals and "subtotal" in entities:
        totals["subtotal"] = _clean_amount(str(entities["subtotal"].get("text")))

    return totals


def _extract_line_items(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    line_items: List[Dict[str, Any]] = []
    raw_items = payload.get("line_items") or payload.get("items")

    if isinstance(raw_items, list):
        for row in raw_items:
            if not isinstance(row, Mapping):
                continue
            normalized_row = {key: row.get(key) for key in row.keys() if key in LINE_ITEM_FIELDS}
            if any(value for value in normalized_row.values()):
                line_items.append(normalized_row)
        return line_items

    tables = payload.get("tables") or payload.get("pages")
    if isinstance(tables, Iterable):
        for table in tables:
            if not isinstance(table, Mapping):
                continue
            cells = table.get("cells") or table.get("rows")
            if not isinstance(cells, list):
                continue
            candidate: Dict[str, Any] = {}
            for cell in cells:
                if not isinstance(cell, Mapping):
                    continue
                header = cell.get("header") or cell.get("column")
                value = cell.get("text") or cell.get("value")
                if header in LINE_ITEM_FIELDS:
                    candidate[header] = value
            if candidate:
                line_items.append(candidate)
    return line_items


def _clean_amount(amount: Optional[str]) -> Optional[str]:
    if not amount:
        return None
    text = str(amount)
    digits = re.findall(r"[0-9]+(?:\.[0-9]+)?", text.replace(",", ""))
    if not digits:
        return None
    return digits[-1]
