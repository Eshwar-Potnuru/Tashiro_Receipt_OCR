import json
from pathlib import Path
p = Path('artifacts/docai_debug_results.json')
if not p.exists():
    print('No docai debug results found at', p)
    raise SystemExit(1)

data = json.loads(p.read_text(encoding='utf-8'))
# file entries are large; we'll scan per-file for missing tax_classification
count = 0
for entry in data.get('files', [])[:500]:
    extracted = entry.get('extracted_data') or {}
    tax_class = extracted.get('tax_classification')
    tax_amount = extracted.get('tax') or extracted.get('tax_amount')
    subtotal = extracted.get('subtotal')
    total = extracted.get('total')
    filename = entry.get('filename') or entry.get('file') or 'unknown'
    if not tax_class:
        count += 1
        print('---')
        print('filename:', filename)
        print('  tax_classification:', tax_class)
        print('  tax_amount:', tax_amount)
        print('  subtotal:', subtotal)
        print('  total:', total)
        raw = entry.get('raw_text') or entry.get('structured_data', {}).get('raw_text')
        print('  raw_text (preview):', (raw or '').replace('\n',' ')[:300])

print('\nTotal missing tax_classification in debug artifacts:', count)
