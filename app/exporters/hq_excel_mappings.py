"""HQ Excel demo mappings (Phase 2E demo scope).

Mapping-only module for Jan 15 demo. No file I/O, no openpyxl, no pandas.
Maps canonical ExtractionResult fields to fixed Excel template headers for two
HQ formats. Demo constraints: expense-only, single receipt, single row, fixed
templates, no accumulation, no 集計シート logic, no carry-over updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ColumnMapping:
    """Represents a mapping from an ExtractionResult field or a fixed/derived value to an Excel column header."""

    header: str              # Excel column header (Japanese, as-is in template)
    source_field: Optional[str] = None  # ExtractionResult attribute name, if pulled directly
    fixed_value: Optional[Any] = None   # Literal value for demo (e.g., "DEMO", "経費")
    derived: Optional[str] = None       # Identifier for derived logic (e.g., tax buckets, invoice flag)
    notes: Optional[str] = None         # Extra context for demo assumptions


# Demo-only derived keys (to be implemented by HQExcelExporter in next step)
DERIVED_INVOICE_FLAG = "invoice_flag"   # returns "有" or "不要"
DERIVED_TAX_10 = "tax_10"               # amount if tax_classification == 10%
DERIVED_TAX_8 = "tax_8"                 # amount if tax_classification == 8%
DERIVED_TAX_EXEMPT = "tax_exempt"       # amount if tax_classification == 非課税
DERIVED_TAX_TOTAL_10 = "tax_total_10"   # optional explicit 10% consumption tax
DERIVED_TAX_TOTAL_8 = "tax_total_8"     # optional explicit 8% consumption tax
DERIVED_TAX_TOTAL_SUM = "tax_total_sum" # optional tax sum


# Format ① – 各個人集計用 _2024 (target a monthly sheet, e.g., "202404")
FORMAT_1_MAPPING: Dict[str, ColumnMapping] = {
    # Demo fixed person
    "担当": ColumnMapping(header="担当", fixed_value="DEMO", notes="Demo-only fixed assignee"),
    # Date
    "支払日": ColumnMapping(header="支払日", source_field="date"),
    # Account category (fixed for demo)
    "勘定科目": ColumnMapping(header="勘定科目", fixed_value="経費", notes="Demo-only account bucket"),
    # Description -> vendor fallback
    "摘要": ColumnMapping(header="摘要", source_field="vendor", notes="Fallback to vendor; exporter may default to 'OCR receipt' when missing"),
    # Income empty for expense-only demo
    "収入": ColumnMapping(header="収入", fixed_value=None, notes="Expense-only demo; leave blank"),
    # Expense total
    "支出": ColumnMapping(header="支出", source_field="total"),
    # Invoice flag derived
    "インボイス": ColumnMapping(header="インボイス", derived=DERIVED_INVOICE_FLAG),
    # Tax buckets
    "10％税込額": ColumnMapping(header="10％税込額", derived=DERIVED_TAX_10),
    "8％税込額": ColumnMapping(header="8％税込額", derived=DERIVED_TAX_8),
    "非課税額": ColumnMapping(header="非課税額", derived=DERIVED_TAX_EXEMPT),
    # Gross total mirrors total
    "税込合計": ColumnMapping(header="税込合計", source_field="total"),
}


# Format ② – 事業所集計テーブル (target a monthly sheet, e.g., "2025年1月")
FORMAT_2_MAPPING: Dict[str, ColumnMapping] = {
    # Date
    "支払日": ColumnMapping(header="支払日", source_field="date"),
    # Work number fixed for demo
    "工番": ColumnMapping(header="工番", fixed_value="DEMO", notes="Demo-only work number"),
    # Description from vendor
    "摘要": ColumnMapping(header="摘要", source_field="vendor"),
    # Person in charge fixed
    "担当者": ColumnMapping(header="担当者", fixed_value="DEMO", notes="Demo-only assignee"),
    # Income left blank
    "収入": ColumnMapping(header="収入", fixed_value=None, notes="Expense-only demo; leave blank"),
    # Expense total
    "支出": ColumnMapping(header="支出", source_field="total"),
    # Invoice flag
    "インボイス": ColumnMapping(header="インボイス", derived=DERIVED_INVOICE_FLAG),
    # Account fixed
    "勘定科目": ColumnMapping(header="勘定科目", fixed_value="経費", notes="Demo-only account bucket"),
    # Tax buckets (inclusive amounts)
    "10％税込額": ColumnMapping(header="10％税込額", derived=DERIVED_TAX_10),
    "8％税込額": ColumnMapping(header="8％税込額", derived=DERIVED_TAX_8),
    "非課税額": ColumnMapping(header="非課税額", derived=DERIVED_TAX_EXEMPT),
    "税込合計": ColumnMapping(header="税込合計", source_field="total"),
    # Optional consumption tax outputs
    "消費税10": ColumnMapping(header="消費税10", derived=DERIVED_TAX_TOTAL_10, notes="Optional; exporter may compute from 10% bucket"),
    "消費税8": ColumnMapping(header="消費税8", derived=DERIVED_TAX_TOTAL_8, notes="Optional; exporter may compute from 8% bucket"),
    "消費税計": ColumnMapping(header="消費税計", derived=DERIVED_TAX_TOTAL_SUM, notes="Optional; exporter may sum tax components"),
}


__all__ = [
    "ColumnMapping",
    "DERIVED_INVOICE_FLAG",
    "DERIVED_TAX_10",
    "DERIVED_TAX_8",
    "DERIVED_TAX_EXEMPT",
    "DERIVED_TAX_TOTAL_10",
    "DERIVED_TAX_TOTAL_8",
    "DERIVED_TAX_TOTAL_SUM",
    "FORMAT_1_MAPPING",
    "FORMAT_2_MAPPING",
]
