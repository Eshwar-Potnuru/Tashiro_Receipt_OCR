"""Generate a report of Document AI extractions (labels A-F) for all sample receipts."""
from pathlib import Path
import json
import sys
import os
# Ensure repo root is on sys.path for direct script execution
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from app.ocr.multi_engine_ocr import MultiEngineOCR
from app.services.receipt_builder import ReceiptBuilder

SAMPLE_DIR = Path('Sample reciepts')
OUT = Path('artifacts/docai_A_to_F_report.json')
OUT.parent.mkdir(parents=True, exist_ok=True)

extensions = ('.png', '.jpg', '.jpeg')
files = [p for p in SAMPLE_DIR.rglob('*') if p.suffix.lower() in extensions]

ocr = MultiEngineOCR()
rb = ReceiptBuilder()
report = {'files': []}

for p in sorted(files):
    try:
        data = p.read_bytes()
    except Exception:
        continue
    res = ocr.extract_structured(data, engine='document_ai')
    sd = res.get('structured_data', {})
    # build extraction result via ReceiptBuilder
    ex = rb.build_from_document_ai(sd, raw_text=res.get('raw_text'))
    report['files'].append({
        'filename': str(p),
        'vendor': ex.vendor,
        'date': ex.date,
        'total': ex.total,
        'invoice_number': ex.invoice_number,
        'tax_classification': ex.tax_classification,
        'expense_category': ex.expense_category,
        'currency': ex.currency,
        'overall_confidence': ex.overall_confidence,
        'confidence_docai': ex.confidence_docai,
        'raw_structured_keys': list(sd.keys()),
    })

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('Wrote', str(OUT))