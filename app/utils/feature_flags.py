"""Feature flag helpers for gated/internal functionality."""

from __future__ import annotations

import os


def is_hq_transfer_enabled() -> bool:
    """Return True when internal HQ transfer endpoints are enabled.

    Default is disabled/off.
    """
    value = (os.getenv("FEATURE_HQ_TRANSFER", "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
