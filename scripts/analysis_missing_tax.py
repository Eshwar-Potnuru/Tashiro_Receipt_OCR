import json
from pathlib import Path
p = Path('artifacts/docai_A_to_F_report.json')
if not p.exists():
    print('Report not found:', p)
    raise SystemExit(1)

data = json.loads(p.read_text(encoding='utf-8'))
files = data.get('files', [])
missing = [f for f in files if not f.get('tax_classification')]
print('total files:', len(files))
print('missing tax_classification:', len(missing))
print('sample missing filenames:')
for f in missing[:10]:
    print(' -', f.get('filename'))

# Show distribution of tax_classification
from collections import Counter
cnt = Counter([f.get('tax_classification') or 'None' for f in files])
print('\nDistribution (top):')
for k,v in cnt.most_common(10):
    print(f'  {k}: {v}')
