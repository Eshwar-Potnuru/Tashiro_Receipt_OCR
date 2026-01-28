"""Excel repository for safe open/save with artifact mirroring (Phase 3A)."""

from __future__ import annotations

import logging
import shutil
import warnings
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook


class ExcelRepository:
    """Thin persistence layer: open/save and optional artifact copy."""

    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parents[2]
        self.artifacts_locations = base_dir / "artifacts" / "accumulation" / "locations"
        self.artifacts_staff = base_dir / "artifacts" / "accumulation" / "staff"
        self.artifacts_locations.mkdir(parents=True, exist_ok=True)
        self.artifacts_staff.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    # -----------------
    # Public API
    # -----------------
    def open(self, path: Path, read_only: bool = False):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*invalid dependency definitions.*")
            return load_workbook(path, read_only=read_only)

    def save(self, workbook, dest_path: Path, *, is_staff: bool = False) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(dest_path)
        self._copy_artifact(dest_path, is_staff=is_staff)

    # -----------------
    # Helpers
    # -----------------
    def _copy_artifact(self, src: Path, *, is_staff: bool) -> None:
        try:
            target_dir = self.artifacts_staff if is_staff else self.artifacts_locations
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target_dir / src.name)
        except Exception as exc:  # best-effort only
            self.logger.warning("Artifact copy failed", extra={"src": str(src), "error": str(exc)})
