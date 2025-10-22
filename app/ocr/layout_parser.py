from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

from app.ocr.ocr_engine import OCRBox


@dataclass
class TextBlock:
    text: str
    box: list[list[float]]
    confidence: float

    @property
    def top(self) -> float:
        return min(point[1] for point in self.box)

    @property
    def bottom(self) -> float:
        return max(point[1] for point in self.box)

    @property
    def left(self) -> float:
        return min(point[0] for point in self.box)

    @property
    def right(self) -> float:
        return max(point[0] for point in self.box)

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass
class LayoutAnalysis:
    blocks: list[TextBlock]
    header_block: Optional[TextBlock]
    totals_candidates: list[TextBlock]
    line_item_candidates: list[TextBlock]


class LayoutParser:
    def __init__(self, merge_threshold: float = 25.0) -> None:
        self.merge_threshold = merge_threshold

    def _merge_boxes_into_blocks(self, boxes: Iterable[OCRBox]) -> list[TextBlock]:
        sorted_boxes = sorted(boxes, key=lambda b: min(point[1] for point in b.box))
        groups: list[list[OCRBox]] = []
        for box in sorted_boxes:
            if not groups:
                groups.append([box])
                continue
            last_group = groups[-1]
            last_box = last_group[-1]
            last_top = min(point[1] for point in last_box.box)
            last_bottom = max(point[1] for point in last_box.box)
            current_top = min(point[1] for point in box.box)
            current_bottom = max(point[1] for point in box.box)
            overlaps_vertically = current_top <= last_bottom and current_bottom >= last_top
            if overlaps_vertically:
                last_group.append(box)
            else:
                groups.append([box])
        blocks: list[TextBlock] = []
        for group in groups:
            group_sorted = sorted(group, key=lambda b: min(point[0] for point in b.box))
            texts = [b.text for b in group_sorted if b.text]
            if not texts:
                continue
            all_points = list(itertools.chain.from_iterable(b.box for b in group_sorted))
            min_x = float(min(point[0] for point in all_points))
            min_y = float(min(point[1] for point in all_points))
            max_x = float(max(point[0] for point in all_points))
            max_y = float(max(point[1] for point in all_points))
            block = TextBlock(
                text=" ".join(texts),
                box=[[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]],
                confidence=float(np.mean([b.confidence for b in group if b.confidence is not None])),
            )
            blocks.append(block)
        return blocks

    def analyze(self, boxes: list[OCRBox]) -> LayoutAnalysis:
        # For receipt OCR, don't merge boxes - treat each line as a separate block
        # This is because receipt text is typically structured as individual lines
        blocks = []
        for box in boxes:
            if box.text.strip():  # Only include non-empty text
                block = TextBlock(
                    text=box.text.strip(),
                    box=box.box,
                    confidence=box.confidence or 0.8
                )
                blocks.append(block)

        if not blocks:
            return LayoutAnalysis(blocks=[], header_block=None, totals_candidates=[], line_item_candidates=[])

        blocks_sorted = sorted(blocks, key=lambda b: b.top)
        header_block = blocks_sorted[0]

        # Identify totals candidates - look for blocks containing total-related keywords
        totals_candidates = []
        for block in blocks_sorted:
            if self._contains_total_keyword(block.text):
                totals_candidates.append(block)

        # If no keyword matches, look at bottom blocks that are numeric-heavy
        if not totals_candidates:
            tail_blocks = blocks_sorted[-8:]  # Check more blocks for Japanese receipts
            numeric_tail = [block for block in tail_blocks if self._is_numeric_heavy(block.text)]
            if numeric_tail:
                totals_candidates = numeric_tail

        # Identify line item candidates
        line_item_candidates = [block for block in blocks_sorted if self._looks_like_line_item(block.text)]

        return LayoutAnalysis(
            blocks=blocks_sorted,
            header_block=header_block,
            totals_candidates=totals_candidates,
            line_item_candidates=line_item_candidates,
        )

    @staticmethod
    def _contains_total_keyword(text: str) -> bool:
        lowered = text.lower()
        # English keywords
        keywords = ["total", "subtotal", "tax", "balance", "amount due"]
        if any(keyword in lowered for keyword in keywords):
            return True
            
        # Japanese keywords for totals section
        japanese_keywords = ["合計", "総計", "小計", "税", "消費税", "現計", "お釣"]
        return any(keyword in text for keyword in japanese_keywords)

    @staticmethod
    def _looks_like_line_item(text: str) -> bool:
        tokens = text.split()
        digits = sum(1 for token in tokens if any(ch.isdigit() for ch in token))
        currency_symbols = sum(1 for token in tokens if any(ch in "$€£¥" for ch in token))
        return digits >= 2 or currency_symbols >= 1

    @staticmethod
    def _is_numeric_heavy(text: str) -> bool:
        stripped = text.replace(",", "").strip()
        if not stripped:
            return False
        digit_count = sum(1 for ch in stripped if ch.isdigit())
        if digit_count >= max(2, len(stripped) // 2):
            return True
        if "%" in stripped and digit_count >= 1:
            return True
        return False
