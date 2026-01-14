"""Demo script: export a precomputed ExtractionResult into HQ Excel formats.

Usage:
    python scripts/demo_hq_export.py

Assumptions:
- No OCR is run here; we load a JSON file containing an ExtractionResult payload.
- Templates live under Template/Formats/.
- Outputs are written to artifacts/demo_exports/ via HQExcelExporter.
- Demo-only: single receipt, single row, expense-only.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.exporters.hq_excel_exporter import HQExcelExporter
from app.models.schema import ExtractionResult


def load_sample_result(json_path: Path) -> ExtractionResult:
    with json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    # Demo-only sanitization: pydantic expects dict for docai_raw_entities/fields.
    for k in ("docai_raw_entities", "docai_raw_fields"):
        v = payload.get(k)
        if v is not None and not isinstance(v, dict):
            payload[k] = None

    return ExtractionResult(**payload)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sample_json = root / "artifacts" / "sample_receipt.json"

    if not sample_json.exists():
        raise FileNotFoundError(f"Sample ExtractionResult JSON not found: {sample_json}")

    receipt = load_sample_result(sample_json)

    # Template paths
    template_dir = root / "Template" / "Formats"
    template_format1 = template_dir / "各個人集計用　_2024.xlsx"
    template_format2 = template_dir / "事業所集計テーブル.xlsx"

    # Export Format ① -> sheet "202404"
    exporter1 = HQExcelExporter(template_format1)
    out1 = exporter1.export_format_1(receipt, sheet_name="202404")
    print(f"Format ① exported to: {out1}")

    # Export Format ② -> sheet "2025年1月"
    exporter2 = HQExcelExporter(template_format2)
    out2 = exporter2.export_format_2(receipt, sheet_name="2025年1月")
    print(f"Format ② exported to: {out2}")


if __name__ == "__main__":
    main()
