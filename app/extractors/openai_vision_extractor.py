# openai_vision_extractor.py
import os
import openai
import json
from dotenv import load_dotenv
load_dotenv()

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

def extract_from_text(text: str) -> dict:
    """
    Sends OCR text to OpenAI for structured JSON extraction.
    Note: keep prompt small and request JSON only.
    """
    if not OPENAI_KEY:
        return {"error": "OPENAI_API_KEY not configured"}
    prompt = (
        "You are a strict JSON-only parser for Japanese receipt text.\n"
        "Input: raw OCR text from a receipt (Japanese). Output: a single JSON object with keys: "
        "vendor, address, date (YYYY-MM-DD), time (HH:MM, optional), invoice_no, subtotal, tax, total, payment, change, items (array).\n"
        "If a field cannot be found, return null for it. RETURN ONLY JSON.\n\n"
        f"TEXT:\n{text}\n\nJSON:"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0
        )
        content = resp.choices[0].message["content"].strip()
        # attempt to parse
        try:
            data = json.loads(content)
            return {"text": text, "structured": data}
        except Exception:
            # fallback: return the raw text so we can inspect
            return {"text": text, "error": "failed to parse json from response", "raw_response": content}
    except Exception as e:
        return {"error": str(e)}
