from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.schema import ExtractionConfig


class ReceiptVerifier:
    def __init__(self) -> None:
        pass

    def verify(self, fields: Dict[str, Optional[float | str]], config: ExtractionConfig) -> tuple[bool, List[str]]:
        issues: List[str] = []

        subtotal = self._to_float(fields.get("subtotal"))
        tax = self._to_float(fields.get("tax"))
        total = self._to_float(fields.get("total"))
        if subtotal is not None and total is not None:
            expected = subtotal + (tax or 0.0)
            if not self._within_tolerance(expected, total, config):
                issues.append("Subtotal and tax do not reconcile with total")
        elif total is None:
            issues.append("Total amount missing")

        date_str = fields.get("date")
        if date_str:
            try:
                date_value = datetime.fromisoformat(str(date_str))
            except ValueError:
                issues.append("Date is not ISO formatted")
            else:
                now = datetime.now(timezone.utc)
                if date_value.tzinfo is None:
                    date_value = date_value.replace(tzinfo=timezone.utc)
                if date_value > now:
                    issues.append("Date is in the future")

        verified = len(issues) == 0
        return verified, issues

    @staticmethod
    def _to_float(value: Optional[float | str]) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, float):
            return value
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _within_tolerance(expected: float, actual: float, config: ExtractionConfig) -> bool:
        absolute_diff = abs(expected - actual)
        relative_diff = absolute_diff / actual if actual != 0 else absolute_diff
        return absolute_diff <= config.verification_tolerance or relative_diff <= config.verification_percent_tolerance
