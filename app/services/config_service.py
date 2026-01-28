"""File-based configuration loader for Phase 2C."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from validators import normalize_location


class ConfigService:
    """Load canonical config snapshots from the filesystem only."""

    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parents[2]
        config_dir = base_dir / "config"

        self.locations_path = config_dir / "locations.json"
        self.staff_config_path = config_dir / "staff_config.json"
        self.vendor_overrides_path = config_dir / "vendor_overrides.json"

        self._locations = None
        self._staff = None
        self._vendor_overrides = None

        self._logger = logging.getLogger(__name__)

    # -----------------
    # Public accessors
    # -----------------
    def get_locations(self) -> List[str]:
        """Return canonical location list from config/locations.json."""
        if self._locations is None:
            self._locations = self._load_locations()
        return list(self._locations)

    def normalize_location(self, raw: Optional[str]) -> Optional[str]:
        """Normalize location using validators.normalize_location with loaded config."""
        cfg = {"locations": self.get_locations(), "synonyms": self._load_locations_synonyms()}
        return normalize_location(raw, cfg)

    def get_staff_for_location(self, canonical_location: str) -> List[Dict[str, str]]:
        """Return staff list for a canonical location from staff_config.json."""
        if self._staff is None:
            self._staff = self._load_staff()
        return self._staff.get(canonical_location, [])

    def get_vendor_canonical(self, vendor_name: Optional[str]) -> Optional[str]:
        """Apply vendor overrides (case-insensitive, first match wins)."""
        if not vendor_name:
            return None
        overrides = self._load_vendor_overrides()
        target = vendor_name.strip().lower()
        matches = []
        for rule in overrides:
            aliases = rule.get("aliases", []) or []
            for alias in aliases:
                if target == str(alias).strip().lower():
                    matches.append(rule)

        if not matches:
            return vendor_name

        if len(matches) > 1:
            self._logger.warning("Multiple vendor overrides matched; using first", extra={"vendor": vendor_name})

        return matches[0].get("canonical_name") or vendor_name

    # -----------------
    # Internal loaders
    # -----------------
    def _load_locations(self) -> List[str]:
        if not self.locations_path.exists():
            return []
        with self.locations_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("locations", []) or []

    def _load_locations_synonyms(self) -> Dict[str, str]:
        if not self.locations_path.exists():
            return {}
        with self.locations_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("synonyms", {}) or {}

    def _load_staff(self) -> Dict[str, List[Dict[str, str]]]:
        resolved = self.staff_config_path.resolve()
        self._logger.info("Staff config path resolved", extra={"path": str(resolved)})
        if not resolved.exists():
            self._logger.warning("Staff config not found", extra={"path": str(resolved)})
            return {}
        with resolved.open("r", encoding="utf-8") as handle:
            data = json.load(handle) or {}
        self._logger.info(
            "Staff config loaded",
            extra={"path": str(resolved), "keys": list(data.keys())},
        )
        return data

    def _load_vendor_overrides(self) -> List[Dict[str, object]]:
        if self._vendor_overrides is not None:
            return self._vendor_overrides
        if not self.vendor_overrides_path.exists():
            self._vendor_overrides = []
            return self._vendor_overrides
        with self.vendor_overrides_path.open("r", encoding="utf-8") as handle:
            self._vendor_overrides = json.load(handle) or []
        return self._vendor_overrides
