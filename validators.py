"""Validation and normalization helpers for Receipt OCR accumulation workflows."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import json
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "locations.json"
DATA_DIR = BASE_DIR / "app" / "Data"
ACCUM_DIR = DATA_DIR / "accumulation"


def load_locations_config() -> Dict[str, Dict[str, str]]:
    """Load canonical locations and synonyms from config/locations.json."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing locations config at {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("locations", [])
    data.setdefault("synonyms", {})
    return data


def discover_locations_from_files() -> List[str]:
    """Return location names inferred from *_Accumulated.xlsx files on disk."""
    if not ACCUM_DIR.exists():
        return []
    discovered: List[str] = []
    for path in ACCUM_DIR.glob("*_Accumulated.xlsx"):
        stem = path.stem
        if stem.endswith("_Accumulated"):
            discovered.append(stem.replace("_Accumulated", ""))
    return sorted(set(discovered))


def get_available_locations() -> Dict[str, Iterable[str]]:
    """Merge config-defined locations with on-disk discoveries."""
    cfg = load_locations_config()
    cfg_locations = cfg.get("locations", [])
    discovered = discover_locations_from_files()
    merged = sorted(dict.fromkeys([*cfg_locations, *discovered]))
    return {"locations": merged, "synonyms": cfg.get("synonyms", {})}


def _canonical_token(raw: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw or "")
    normalized = normalized.strip().lower()
    normalized = normalized.replace(" ", "").replace("　", "")
    return normalized


def normalize_location(raw: Optional[str], config: Optional[Dict[str, Dict[str, str]]] = None) -> Optional[str]:
    """Normalize business location using configured synonyms and discoveries."""
    if not raw:
        return None
    config = config or get_available_locations()
    canonical = config.get("locations", [])
    synonyms = config.get("synonyms", {})

    token = _canonical_token(raw)
    if not token:
        return None

    for name in canonical:
        if token == _canonical_token(name):
            return name

    for key, mapped in synonyms.items():
        if token == _canonical_token(key):
            return mapped

    for name in canonical:
        if token in _canonical_token(name):
            return name
    return None


def normalize_number(value: Optional[str]) -> Optional[str]:
    """Normalize order/invoice numbers (strip symbols, unify width, uppercase)."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[-_#。、.,]", "", normalized)
    normalized = normalized.strip()
    return normalized.upper() if normalized else None


def parse_date(value: Optional[str]) -> Optional[str]:
    """Parse assorted date formats and return ISO string (YYYY-MM-DD)."""
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value.strip())
    candidates = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y年%m月%d日",
    ]
    for fmt in candidates:
        try:
            dt = datetime.strptime(normalized, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def validate_required_fields(data: Dict[str, object]) -> None:
    """Validate required OCR fields according to accumulation requirements."""
    location = data.get("business_location") or data.get("location") or data.get("business_office")
    order_number = data.get("order_number") or data.get("orderNo")
    invoice_number = data.get("invoice_number") or data.get("invoiceNo")

    missing: List[str] = []
    if not location:
        missing.append("business_location")
    if not (order_number or invoice_number):
        missing.append("order_number_or_invoice_number")

    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
