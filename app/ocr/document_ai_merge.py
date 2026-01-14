"""Conflict-aware merge helpers for Document AI structured payloads.

TODO: Surface merge decisions through service-level telemetry once pipelines are wired.
"""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Dict, List, Mapping

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_MARGIN = 0.05


def merge_structured_data(
    base: Mapping[str, Any] | None,
    document_ai: Mapping[str, Any],
    *,
    confidence_margin: float = DEFAULT_CONFIDENCE_MARGIN,
) -> Dict[str, Any]:
    """Merge Document AI fields into an existing structured payload."""

    result: Dict[str, Any] = deepcopy(base) if base else {}
    result.setdefault("raw_text", document_ai.get("raw_text", ""))
    result.setdefault("entities", {})
    result.setdefault("confidence_scores", {})
    result.setdefault("line_items", [])
    result.setdefault("totals", {})
    for key in ("docai_raw_entities", "docai_raw_fields"):
        if key not in result and key in document_ai:
            result[key] = document_ai.get(key)

    _merge_entities(
        result["entities"],
        result["confidence_scores"],
        document_ai.get("entities", {}),
        document_ai.get("confidence_scores", {}),
        confidence_margin,
    )

    _merge_totals(result["totals"], document_ai.get("totals", {}))
    _merge_line_items(result["line_items"], document_ai.get("line_items", []))
    result["raw_text"] = _merge_raw_text(result.get("raw_text", ""), document_ai.get("raw_text", ""))

    return result


def _merge_entities(
    base_entities: Dict[str, Any],
    base_confidence: Dict[str, float],
    document_ai_entities: Mapping[str, Any],
    document_ai_confidence: Mapping[str, float],
    confidence_margin: float,
) -> None:
    for field, candidate in document_ai_entities.items():
        candidate_text = _extract_text(candidate)
        if not candidate_text:
            continue

        candidate_conf = float(document_ai_confidence.get(field, candidate.get("confidence", 0.0) if isinstance(candidate, Mapping) else 0.0))
        current_conf = float(base_confidence.get(field, 0.0))
        current_text = _extract_text(base_entities.get(field)) if field in base_entities else ""

        should_replace = not current_text
        if not should_replace:
            if candidate_conf >= current_conf + confidence_margin:
                should_replace = True
            elif candidate_conf >= current_conf and candidate_text != current_text:
                should_replace = True

        if should_replace:
            base_entities[field] = {"text": candidate_text, "source": "document_ai"}
            base_confidence[field] = min(max(candidate_conf, 0.0), 1.0)
            logger.debug("Document AI set entity '%s' => %s", field, candidate_text)


def _merge_totals(base_totals: Dict[str, Any], candidate_totals: Mapping[str, Any]) -> None:
    for key in ("total", "subtotal", "tax"):
        candidate_value = candidate_totals.get(key)
        if candidate_value in (None, ""):
            continue
        if key not in base_totals or not base_totals[key]:
            base_totals[key] = candidate_value
        else:
            current_value = str(base_totals[key])
            if str(candidate_value) != current_value:
                base_totals[key] = _pick_numeric(current_value, candidate_value)


def _merge_line_items(base_items: List[Dict[str, Any]], candidate_items: List[Mapping[str, Any]]) -> None:
    if not candidate_items:
        return
    if not base_items:
        base_items.extend(deepcopy(item) for item in candidate_items)
        return

    existing_signatures = { _line_item_signature(item) for item in base_items }
    for item in candidate_items:
        signature = _line_item_signature(item)
        if signature in existing_signatures:
            continue
        base_items.append(deepcopy(dict(item)))
        existing_signatures.add(signature)


def _merge_raw_text(primary: str, secondary: str) -> str:
    if not primary:
        return secondary or ""
    if not secondary:
        return primary
    if secondary in primary:
        return primary
    return primary + "\n" + secondary


def _pick_numeric(current: Any, candidate: Any) -> Any:
    try:
        current_value = float(str(current).replace(",", ""))
        candidate_value = float(str(candidate).replace(",", ""))
    except ValueError:
        return candidate
    return candidate if candidate_value >= current_value else current


def _line_item_signature(item: Mapping[str, Any]) -> str:
    description = str(item.get("description") or item.get("item") or "").strip().lower()
    amount = str(item.get("amount") or item.get("total") or "").strip()
    return f"{description}|{amount}"


def _extract_text(value: Any) -> str:
    if isinstance(value, Mapping):
        if "text" in value and isinstance(value["text"], str):
            return value["text"].strip()
        if "value" in value and isinstance(value["value"], str):
            return value["value"].strip()
    if isinstance(value, str):
        return value.strip()
    return ""
