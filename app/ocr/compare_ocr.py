# compare_ocr.py
from difflib import SequenceMatcher
import math

def text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def dynamic_confidence(a_text: str, b_text: str) -> float:
    sim = text_similarity(a_text, b_text)
    # scale to [0.6, 0.95]
    return 0.6 + 0.35 * sim

def compare_and_choose(primary: dict, secondary: dict) -> dict:
    """
    primary and secondary should be normalized outputs: {'text':..., 'regions':...}
    This returns a combined dict with 'text' chosen and 'confidence'
    """
    a = primary.get("text", "")
    b = secondary.get("text", "")
    conf = dynamic_confidence(a, b)
    # if very similar, pick the one with longer text (more info)
    if text_similarity(a,b) > 0.85:
        chosen = a if len(a) >= len(b) else b
    else:
        # prefer primary if non-empty
        chosen = a if a else b
    return {"text": chosen, "confidence": conf, "sources": {"primary": primary.get("engine"), "secondary": secondary.get("engine")}}