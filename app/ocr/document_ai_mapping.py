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
    # Common variations and noisy labels observed in Document AI outputs
    "price": "total",
    "amount": "total",
    "total_price": "total",
    "grand_total": "total",

    "subtotal_amount": "subtotal",
    "subtotal": "subtotal",

    "tax_amount": "tax",
    "vat_amount": "tax",
    "tax": "tax",

    "supplier_name": "vendor",
    "vendor_name": "vendor",
    "merchant_name": "vendor",
    "store_name": "vendor",

    # Date/time variations
    "receipt_date": "date",
    "invoice_date": "date",
    "date": "date",
    "date_time": "date",

    # Invoice/receipt identifiers
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

    # When entities are provided as a mapping, ensure the 'date' keys actually look like dates
    # (avoid promoting phone numbers that Document AI sometimes classifies as dates)
    for k, v in list(entities.items()):
        if k == 'date' and v and isinstance(v, dict):
            if not _looks_like_date(str(v.get('text') or '')):
                # Remove suspicious date entity to allow raw text fallback
                entities.pop(k, None)
                confidences.pop(k, None)

    # Invoice detection: prefer invoice numbers that start with 'T' (e.g., T12345) found in raw text
    # and promote them to the canonical 'invoice_number' entity if none present.
    if 'invoice_number' not in entities:
        invoice_guess = _find_invoice_in_text(document.raw_text)
        if invoice_guess:
            entities['invoice_number'] = {'text': invoice_guess}
            confidences.setdefault('invoice_number', 0.5)

    # Persist normalized entities and confidences on the document before further processing
    document.entities = entities
    document.confidence_scores = confidences
    # Derive totals now that entities are finalized
    document.totals = _extract_totals(payload, entities)

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

    data = document.asdict()
    # Provide convenient top-level total/subtotal/tax keys for downstream consumers
    totals = document.totals or {}
    if totals.get("total") is not None:
        data["total"] = totals.get("total")
    if totals.get("tax") is not None:
        data["tax"] = totals.get("tax")
    if totals.get("subtotal") is not None:
        data["subtotal"] = totals.get("subtotal")

    # Promote common entities to top-level keys for easier consumption by builders
    entities = document.entities or {}
    if entities.get("vendor"):
        data["vendor"] = entities.get("vendor").get("text")
    if entities.get("date"):
        date_text = entities.get("date").get("text")
        if _looks_like_date(date_text):
            data["date"] = date_text
        else:
            # If the entity looks suspicious (e.g., a phone number), attempt to find a date in raw_text
            date_guess = _find_date_in_text(document.raw_text)
            if date_guess:
                data["date"] = date_guess
    # If no date promoted yet, attempt raw-text fallback
    if not data.get("date"):
        date_guess = _find_date_in_text(document.raw_text)
        if date_guess:
            data["date"] = date_guess
    if entities.get("invoice_number"):
        data["invoice_number"] = entities.get("invoice_number").get("text")

    # Provide a simple aggregated confidence metric for Document AI (if numeric confidences are present)
    confs = document.confidence_scores or {}
    numeric_confs = [v for v in confs.values() if isinstance(v, (int, float))]
    if numeric_confs:
        data["confidence_docai"] = float(sum(numeric_confs) / len(numeric_confs))
    else:
        data["confidence_docai"] = None

    # Vendor fallback: if no explicit vendor, try the first non-empty, non-numeric top line
    if not data.get("vendor"):
        vendor_guess = _extract_vendor_from_text(document.raw_text)
        if vendor_guess:
            data["vendor"] = vendor_guess

    # Ensure totals are present: if not set earlier, re-run totals extraction from raw payload/text
    if not data.get("total"):
        fallback_totals = _extract_totals(payload, document.entities or {})
        if fallback_totals.get("total"):
            data["total"] = fallback_totals.get("total")
            data["totals"] = fallback_totals
        else:
            # final fallback: explicitly search labeled lines in raw text
            labeled = _find_labelled_total_in_text(document.raw_text)
            if labeled:
                data["total"] = labeled
                data["totals"] = {"total": labeled}

    return data


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
            canonical = DOCUMENT_AI_ENTITY_MAP.get(key, key)
            # If canonical is 'total', ensure the provided value resembles money
            if canonical == "total":
                textval = ""
                if isinstance(value, Mapping):
                    textval = _extract_text(value) or str(value.get("value", ""))
                else:
                    textval = str(value)
                if not _looks_like_money(textval):
                    continue
            entities[canonical] = _wrap_value(value)
            confidences[canonical] = _coerce_confidence(value)
        return entities, confidences

    if isinstance(raw_entities, Iterable):
        for entry in raw_entities:
            if not isinstance(entry, Mapping):
                continue

            # Some Document AI responses wrap properties inside a generic container
            # e.g., { "type_": "generic_entities", "properties": [ {"type": "phone", ...}, ... ] }
            properties = entry.get("properties") if isinstance(entry, Mapping) else None
            if isinstance(properties, Iterable):
                for prop in properties:
                    if not isinstance(prop, Mapping):
                        continue
                    entity_type = prop.get("type") or prop.get("type_") or prop.get("field_type")
                    if not entity_type:
                        continue
                    text_value = _extract_text(prop)
                    canonical = DOCUMENT_AI_ENTITY_MAP.get(entity_type, entity_type)
                    # If multiple properties map to the same canonical key, prefer later ones.
                    # Add heuristics: only accept totals that look like money values to avoid mapping IDs/postal codes.
                    if canonical == "total":
                        if not _looks_like_money(text_value):
                            # Skip spurious total-like entries that are not monetary
                            continue
                    # Avoid accepting date-like phone numbers as dates
                    if canonical == "date" and not _looks_like_date(text_value):
                        continue
                    entities[canonical] = {"text": text_value, "raw": prop}
                    confidences[canonical] = float(prop.get("confidence", 0.0))
                continue

            entity_type = entry.get("type") or entry.get("type_") or entry.get("field_type")
            if not entity_type:
                continue
            text_value = _extract_text(entry)
            canonical = DOCUMENT_AI_ENTITY_MAP.get(entity_type, entity_type)
            # Only accept 'total' if it resembles a monetary amount
            if canonical == "total" and not _looks_like_money(text_value):
                continue
            # Only accept 'date' if it resembles a date; avoid accepting phones
            if canonical == "date" and not _looks_like_date(text_value):
                continue
            entities[canonical] = {"text": text_value, "raw": entry}
            confidences[canonical] = float(entry.get("confidence", 0.0))
        return entities, confidences

    return entities, confidences


# --- Helper heuristics used by mapping ---

def _find_labelled_total_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Normalize and split lines, skipping empties
    lines = [l.strip() for l in text.splitlines() if l and l.strip()]
    if not lines:
        return None

    # Heuristic 1: scan bottom-up for labeled total lines (prefer lines near document end)
    # Check the last N lines where totals typically appear on receipts
    N = 8
    for idx in range(len(lines) - 1, max(-1, len(lines) - N - 1), -1):
        line = lines[idx]
        if any(k in line for k in ("合計", "合　計", "TOTAL", "Total", "合計額")):
            # Try the same line first
            amt = _clean_amount(line)
            if amt:
                return amt
            # Try adjacent lines (above and below) since amount may be on a separate line
            if idx + 1 < len(lines):
                amt = _clean_amount(lines[idx + 1])
                if amt:
                    return amt
            if idx - 1 >= 0:
                amt = _clean_amount(lines[idx - 1])
                if amt:
                    return amt

    # Fallback: scan all lines top-down (legacy behavior)
    for line in lines:
        if any(k in line for k in ("合計", "合　計", "TOTAL", "Total", "合計額")):
            amt = _clean_amount(line)
            if amt:
                return amt
    return None


def _find_all_amounts(text: str) -> List[float]:
    if not text:
        return []
    candidates = re.findall(r"\d+[\d,\.]*\d|\d+", text)
    results: List[float] = []
    for cand in candidates:
        s = cand.replace(',', '')
        # Heuristic: treat '.' as thousands sep if group after last '.' has 3 digits
        if '.' in s:
            last_dot = s.split('.')[-1]
            if len(last_dot) == 3:
                s = s.replace('.', '')
        # Skip implausibly long digit sequences (IDs/postal codes)
        digits_only = re.sub(r"[^0-9]", "", s)
        if len(digits_only) > 10:
            continue
        try:
            val = float(s)
            # Exclude non-positive values
            if val <= 0:
                continue
            results.append(val)
        except Exception:
            continue
    return results


def _looks_like_money(text: str) -> bool:
    if not text:
        return False
    # Reject invoice identifiers like 'T123456' which are not monetary amounts
    if re.match(r"^\s*T\d+\b", text):
        return False
    if any(sym in text for sym in ("¥", "￥", "円")):
        return True
    # Clean text and count digits
    digits = re.sub(r"[^0-9]", "", text)
    if not digits or len(digits) < 1:
        return False
    # Postal codes and IDs tend to be very long; money values are typically shorter
    if len(digits) > 10:
        return False
    # If it contains comma or dot separators, more likely money
    if "," in text or "." in text:
        return True
    # Otherwise, if it has at least 3 digits, consider it money-ish
    if len(digits) >= 3:
        return True
    return False


def _looks_like_date(text: str) -> bool:
    if not text:
        return False
    txt = text.strip()
    # Avoid matching words that include date characters but are not dates (e.g., '年代', '年齢')
    if re.search(r"\b年代\b|\b年齢\b", txt):
        return False
    # ISO-like or explicit Japanese full-date patterns (preferred)
    if re.search(r"\b20\d{2}年\b|\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", txt):
        return True
    if re.search(r"\d{1,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", txt):
        return True
    if re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*日", txt):
        return True
    # If digits are adjacent to date markers, treat as date only when there is a plausible numeric context
    if re.search(r"\d+[年月日]", txt):
        if re.search(r"\d{4}[年]|\d{1,2}月\s*\d{1,2}日", txt):
            return True
    # Avoid treating pure time strings like '18:34' as dates
    if re.search(r"^\d{1,2}:\d{2}$", txt):
        return False
    return False


def _find_date_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    lines = [l.strip() for l in text.splitlines() if l and l.strip()]
    # First pass: look for explicit, parseable date patterns (preferred)
    for line in lines:
        # YYYY年M月D日 or YYYY-M-D
        m = re.search(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日", line)
        if m:
            return m.group(0)
        m2 = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", line)
        if m2:
            return m2.group(0)
        # Also accept MM月DD日 patterns when they appear with numbers
        m3 = re.search(r"\d{1,2}月\s*\d{1,2}日", line)
        if m3:
            return m3.group(0)

    # Second pass: if no explicit matches, look for a line containing a 4-digit year and return a numeric context
    for line in lines:
        y = re.search(r"20\d{2}", line)
        if y:
            # Try to extract around the year to avoid returning unrelated promotional lines
            start = max(0, y.start() - 6)
            end = min(len(line), y.end() + 12)
            snippet = line[start:end]
            return snippet

    return None


def _looks_like_invoice_number(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\bT\d{3,}\b", text.strip()))


def _find_invoice_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Look for a T-prefixed invoice id in lines, prefer isolated token
    for line in text.splitlines():
        m = re.search(r"\bT\d{3,}\b", line)
        if m:
            return m.group(0)
    # Also search the entire text as last resort
    m = re.search(r"\bT\d{3,}\b", text)
    if m:
        return m.group(0)
    return None


def _extract_vendor_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Consider first few lines, prefer lines with letters/kanji and longer than 2 chars,
    # and avoid obvious non-vendor keywords (e.g., 'アルバイト', '募集', '電話', 'TEL')
    blacklist = ("アルバイト", "募集", "TEL", "電話", "No.", "No", "〒", "〇●")
    for line in (l.strip() for l in text.splitlines() if l and l.strip()):
        if any(b in line for b in blacklist):
            continue
        # Skip lines that look like phone numbers or addresses
        if re.search(r"\d{2,4}[-\d\s]*\d{2,4}", line):
            continue
        # Strip common leading numeric markers or bullets (e.g., '7 ', '1)', 'No. ')
        cleaned = re.sub(r"^[\s\-\.\)\(0-9]+", "", line).strip()
        if not cleaned:
            continue
        # Prefer lines containing CJK characters (likely vendor names), fallback to general text
        if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", cleaned):
            if len(cleaned) >= 2:
                return cleaned
        if len(cleaned) >= 3 and not re.match(r"^[0-9\s\-/()\\]+$", cleaned):
            return cleaned
    return None


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
    # Some Document AI payloads only provide text anchors. Attempt to reconstruct from text_anchor.content
    text_anchor = entry.get("text_anchor") if isinstance(entry, Mapping) else None
    if isinstance(text_anchor, Mapping):
        # In some responses content is at text_anchor.content, or nested segments; handle both.
        content = text_anchor.get("content")
        if isinstance(content, str) and content.strip():
            return content
        # Some anchors have segments with start/end indexes; fall back to empty if unavailable
    return ""


def _extract_totals(payload: Mapping[str, Any], entities: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, Any] = {}
    candidate_sources = [payload.get("totals"), payload.get("summary"), payload.get("total"), payload.get("amounts")]

    # Prefer explicit totals if provided
    for source in candidate_sources:
        if isinstance(source, Mapping):
            for key, value in source.items():
                canonical = DOCUMENT_AI_ENTITY_MAP.get(key, key)
                if canonical == "total" and value:
                    cleaned = _clean_amount(str(value))
                    if cleaned:
                        totals["total"] = cleaned
                if canonical == "tax":
                    tax_val = _clean_amount(str(value))
                    if tax_val:
                        totals["tax"] = tax_val
                if canonical == "subtotal":
                    sub_val = _clean_amount(str(value))
                    if sub_val:
                        totals["subtotal"] = sub_val

    # Fall back to entities
    if "total" not in totals:
        entity = entities.get("total") or entities.get("total_amount") or entities.get("grand_total")
        if entity:
            text = str(entity.get("text"))
            if _looks_like_money(text):
                cleaned = _clean_amount(text)
                if cleaned:
                    totals["total"] = cleaned

    # If still missing, scan raw_text for labeled total lines or the largest monetary value
    # Treat missing or implausible totals (empty, zero, or extremely long digit sequences) as absent
    total_val = str(totals.get("total")) if totals.get("total") is not None else ""
    if ("total" not in totals) or total_val.strip() in ("", "0", "0.0") or len(re.sub(r"\D", "", total_val)) > 10:
        raw_text = payload.get("text") or payload.get("raw_text") or ""
        labeled = _find_labelled_total_in_text(raw_text)
        if labeled:
            totals["total"] = labeled
        else:
            # As a last resort pick the largest numeric currency-looking value
            all_values = _find_all_amounts(raw_text)
            if all_values:
                chosen = max(all_values)
                # normalize to integer string when appropriate
                if abs(chosen - int(chosen)) < 1e-9:
                    totals["total"] = str(int(chosen))
                else:
                    totals["total"] = str(chosen)

    # Tax/subtotal fallbacks from entities if still missing
    if "tax" not in totals and "tax" in entities:
        tax_val = _clean_amount(str(entities["tax"].get("text")))
        if tax_val:
            totals["tax"] = tax_val
    if "subtotal" not in totals and "subtotal" in entities:
        sub_val = _clean_amount(str(entities["subtotal"].get("text")))
        if sub_val:
            totals["subtotal"] = sub_val

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
    """Normalize a monetary amount to a plain numeric string (no commas).

    Handles common OCR artifacts like currency symbols, parentheses, '内', and thousands
    separators expressed as commas or dots (e.g., "¥7.200" -> "7200"). Returns
    None if no numeric value can be parsed.
    """
    if not amount:
        return None
    text = str(amount)
    # Remove common currency symbols and annotations
    text = text.replace("¥", "").replace("￥", "").replace("\\", "").replace("内", "").replace("(税込)", "").strip()
    # Remove any surrounding parentheses or trailing non-numeric chars
    text = text.strip("() ")
    # Replace full-width commas/dots
    text = text.replace("，", ",").replace("．", ".")

    # Extract candidate numbers like 1,234.56 or 1.234 or 1234
    candidates = re.findall(r"\d+[\d,\.]*\d|\d+", text)
    if not candidates:
        return None

    normalized_candidates: List[float] = []
    for cand in candidates:
        s = cand.replace(',', '')
        # Heuristic: if '.' appears and the group after last '.' is exactly 3 digits, treat '.' as thousands sep
        if '.' in s:
            last_dot_part = s.split('.')[-1]
            if len(last_dot_part) == 3 and len(s.split('.')[0]) > 0:
                s = s.replace('.', '')
        try:
            # Skip candidates that would produce implausibly long integer values (likely IDs/postal codes)
            digits_only = re.sub(r"[^0-9]", "", s)
            if len(digits_only) > 10:
                continue
            val = float(s)
            normalized_candidates.append(val)
        except Exception:
            continue

    if not normalized_candidates:
        return None

    # Prefer the largest value as the total heuristic (totals are usually the largest numbers)
    chosen = max(normalized_candidates)
    # Return as integer string if whole number, else keep decimal
    if abs(chosen - int(chosen)) < 1e-9:
        return str(int(chosen))
    return str(chosen)
