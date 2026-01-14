"""ValidationService: non-blocking advisory checks for ExtractionResult.

This service centralizes lightweight validation so routes/controllers can call a
single entrypoint without embedding mapping or validation logic. All checks are
advisory: no exceptions are raised and schema is not modified.
"""

from __future__ import annotations

from typing import List

from app.models.schema import ExtractionConfig, ExtractionResult


class ValidationService:
    """Perform advisory validations on an ExtractionResult.

    The validate method mutates the provided result in place (appending issues
    without overwriting existing entries) and returns the same instance for
    convenience. All validations are idempotent: repeated calls will not
    duplicate issues.
    """

    def validate(self, result: ExtractionResult, config: ExtractionConfig) -> ExtractionResult:
        # Ensure list fields exist for safe appends.
        if result.missing_required_fields is None:
            result.missing_required_fields = []
        if result.warnings is None:
            result.warnings = []
        if result.verification_issues is None:
            result.verification_issues = []

        # Helper to append unique entries.
        def _add_unique(target: List[str], value: str) -> None:
            if value not in target:
                target.append(value)

        # Required field presence checks (vendor, date, total).
        for field_name in ("vendor", "date", "total"):
            value = getattr(result, field_name, None)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                _add_unique(result.missing_required_fields, field_name)
                _add_unique(result.verification_issues, f"missing_{field_name}")

        # Financial consistency check using normalized fields when all are present.
        subtotal = result.normalized_subtotal
        tax = result.normalized_tax
        total = result.normalized_total
        if subtotal is not None and tax is not None and total is not None:
            expected_total = subtotal + tax
            delta = expected_total - total
            abs_delta = abs(delta)
            rel_delta = abs_delta / total if total else 0.0

            fails_abs = abs_delta > config.verification_tolerance
            fails_rel = rel_delta > config.verification_percent_tolerance
            if fails_abs and fails_rel:
                _add_unique(result.warnings, "financial_inconsistency")
                _add_unique(result.verification_issues, "financial_inconsistency")

        # Verified flag reflects presence of issues (non-blocking advisory).
        result.verified = len(result.verification_issues) == 0
        return result


__all__ = ["ValidationService"]
