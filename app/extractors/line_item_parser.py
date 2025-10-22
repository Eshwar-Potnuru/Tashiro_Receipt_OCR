from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from app.models.schema import LineItem
from app.ocr.layout_parser import LayoutAnalysis

LINE_ITEM_REGEXES = [
    re.compile(
        r"^(?P<description>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<unit>\d+(?:\.\d+)?)\s+(?P<total>\d+(?:\.\d+)?)$"
    ),
    re.compile(
        r"^(?P<description>.+?)\s+x\s*(?P<qty>\d+(?:\.\d+)?)\s+(?P<unit>\d+(?:\.\d+)?)\s+(?P<total>\d+(?:\.\d+)?)$",
        re.IGNORECASE,
    ),
]


@dataclass
class ParsedLineItem:
    item: LineItem
    confidence: float


class LineItemParser:
    def parse(self, raw_text: str, layout: LayoutAnalysis) -> List[ParsedLineItem]:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        parsed_items: List[ParsedLineItem] = []
        for line in lines:
            match = self._match_line(line)
            if not match:
                continue
            description = match.group("description").strip()
            qty = float(match.group("qty"))
            unit_price = float(match.group("unit"))
            total_price = float(match.group("total"))
            confidence = 0.7
            line_item = LineItem(
                description=description,
                qty=qty,
                unit_price=unit_price,
                total_price=total_price,
                confidence=confidence,
            )
            parsed_items.append(ParsedLineItem(item=line_item, confidence=confidence))
        if not parsed_items:
            return []
        return parsed_items

    @staticmethod
    def _match_line(line: str) -> re.Match[str] | None:
        for regex in LINE_ITEM_REGEXES:
            match = regex.match(line)
            if match:
                return match
        return None
