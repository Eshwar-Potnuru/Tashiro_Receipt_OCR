# enhanced_japanese_ocr.py
import re

def correct_japanese_text(text: str, confidence: float = 0.9) -> str:
    """
    Conservative corrections: only apply when confidence < threshold.
    """
    if not text:
        return text
    if confidence >= 0.85:
        return text
    # common fixes mapping
    fixes = {
        "レシ一ト": "レシート",
        "合 計": "合計",
        "小 計": "小計",
        "消費 税": "消費税",
    }
    for k, v in fixes.items():
        text = text.replace(k, v)
    # normalize repeated spaces
    text = re.sub(r"\s+", " ", text)
    return text
