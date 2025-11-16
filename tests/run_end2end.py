# tests/run_end2end.py
from PIL import Image
from app.ocr.multi_engine_ocr import process_image_file
img = Image.open("tests/sample_receipt_01.jpg")
res = process_image_file(img)
import json, pprint
pprint.pprint(res)
with open("artifacts/ocr_results/last_result.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print("Saved to artifacts/ocr_results/last_result.json")
