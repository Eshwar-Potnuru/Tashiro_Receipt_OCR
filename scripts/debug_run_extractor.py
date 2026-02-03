import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.extractors.enhanced_field_extractor import EnhancedFieldExtractor

ext=EnhancedFieldExtractor()
structured={'tax':'100','subtotal':'1000'}
res=ext.extract_fields_with_document_ai(structured, raw_text='')
print('RESULT:', res)
print('tax_category:', res.get('tax_category'))

# replicate parsing logic
import re
s='100'
sub='1000'
def to_float(s):
    try:
        ss=re.sub(r"[^0-9\.\-]", "", str(s))
        return float(ss) if ss not in ("","-") else None
    except:
        return None
print('parsed tax:', to_float(s), 'parsed subtotal:', to_float(sub))
