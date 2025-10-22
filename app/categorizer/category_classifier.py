from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from app.models.schema import LineItem

DEFAULT_CATEGORY_KEYWORDS: Dict[str, Sequence[str]] = {
    "meals": ("meal", "dining", "restaurant", "food", "cafe", "coffee"),
    "travel": ("train", "bus", "flight", "ticket", "taxi", "uber", "lyft", "gas"),
    "lodging": ("hotel", "inn", "ryokan", "lodging"),
    "supplies": ("supply", "material", "stationery", "office", "paper", "pen"),
    "utilities": ("electric", "water", "internet", "utility"),
    "other": (),
}


@dataclass
class CategorizationResult:
    line_items: List[LineItem]
    category_summary: Dict[str, float]
    primary_category: Optional[str]


class CategoryClassifier:
    """Simple keyword-based classifier for receipt line items."""

    def __init__(
        self,
        keyword_map: Optional[Dict[str, Sequence[str]]] = None,
        default_category: str = "other",
    ) -> None:
        self.keyword_map = keyword_map or DEFAULT_CATEGORY_KEYWORDS
        self.default_category = default_category

    def classify(self, line_items: Iterable[LineItem], raw_text: str | None = None) -> CategorizationResult:
        categorized_items: List[LineItem] = []
        summary: Dict[str, float] = defaultdict(float)

        for item in line_items:
            category = self._classify_description(item.description, raw_text)
            item.category = category
            categorized_items.append(item)

            if item.total_price is not None:
                try:
                    summary[category] += float(item.total_price)
                except (TypeError, ValueError):
                    continue

        primary_category = max(summary, key=summary.get) if summary else None
        return CategorizationResult(line_items=categorized_items, category_summary=dict(summary), primary_category=primary_category)

    def _classify_description(self, description: str, raw_text: str | None = None) -> str:
        haystack = description.lower()
        if raw_text:
            haystack = f"{haystack}\n{raw_text.lower()}"

        for category, keywords in self.keyword_map.items():
            for keyword in keywords:
                if keyword and keyword in haystack:
                    return category
        return self.default_category
