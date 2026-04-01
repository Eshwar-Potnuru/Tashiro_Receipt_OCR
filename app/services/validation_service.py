"""ValidationService: non-blocking advisory checks for ExtractionResult.

This service centralizes lightweight validation so routes/controllers can call a
single entrypoint without embedding mapping or validation logic. All checks are
advisory by default: no exceptions are raised and schema is not modified.

Phase 12A-1 Enhancement:
    ENFORCE_VALIDATION flag controls blocking behavior:
    - When False (default): Advisory mode - validate() runs, issues logged, no blocking
    - When True: Enforcement mode - validate_for_send() raises ValidationEnforcementError
      if blocking issues are found

Phase 12A-4 Integration:
    Added to_contract_result() method for Phase 12 contract compatibility.
    This allows interoperability with ValidationResult from phase12_contracts.

Environment Variable:
    ENFORCE_VALIDATION=true|false|1|0 (default: false)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from app.models.schema import ExtractionConfig, ExtractionResult
from app.models.phase12_contracts import (
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
)


# Phase 12A-1: Validation enforcement feature flag
# Default: false - preserves existing advisory-only behavior
# Set ENFORCE_VALIDATION=true to block sends with validation issues
ENFORCE_VALIDATION = os.environ.get("ENFORCE_VALIDATION", "false").lower() in ("1", "true", "yes")


@dataclass
class ValidationEnforcementError(Exception):
    """Raised when validation enforcement blocks an operation.
    
    Contains structured error information for API error responses.
    
    Attributes:
        message: Human-readable error description
        verification_issues: List of specific validation failures
        missing_required_fields: List of missing required field names
        receipt_id: Optional receipt ID for error tracking
    """
    message: str
    verification_issues: List[str] = field(default_factory=list)
    missing_required_fields: List[str] = field(default_factory=list)
    receipt_id: Optional[str] = None
    
    def __str__(self) -> str:
        return self.message
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization in HTTP responses."""
        return {
            "error_code": "VALIDATION_FAILED",
            "message": self.message,
            "verification_issues": self.verification_issues,
            "missing_required_fields": self.missing_required_fields,
            "receipt_id": self.receipt_id,
        }


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
    
    def has_blocking_issues(self, result: ExtractionResult) -> bool:
        """Check if result has issues that should block send operations.
        
        Args:
            result: ExtractionResult to check (should be pre-validated)
            
        Returns:
            True if there are blocking validation issues, False otherwise
        """
        return len(result.verification_issues) > 0
    
    def validate_for_send(
        self,
        result: ExtractionResult,
        config: Optional[ExtractionConfig] = None,
        enforce: Optional[bool] = None,
        receipt_id: Optional[str] = None,
    ) -> ExtractionResult:
        """Validate result for send operation, optionally enforcing validation.
        
        This method combines validate() with enforcement logic. When enforcement
        is enabled and blocking issues are found, raises ValidationEnforcementError.
        
        Args:
            result: ExtractionResult to validate
            config: Optional ExtractionConfig (defaults to ExtractionConfig())
            enforce: Override ENFORCE_VALIDATION flag (None = use environment)
            receipt_id: Optional receipt ID for error tracking
            
        Returns:
            Validated ExtractionResult (if no blocking issues or enforcement disabled)
            
        Raises:
            ValidationEnforcementError: If enforcement enabled and blocking issues found
        """
        if config is None:
            config = ExtractionConfig()
        
        # Run advisory validation first
        validated = self.validate(result, config)
        
        # Determine enforcement mode
        should_enforce = enforce if enforce is not None else ENFORCE_VALIDATION
        
        # If enforcement enabled and has blocking issues, raise
        if should_enforce and self.has_blocking_issues(validated):
            issues = validated.verification_issues or []
            missing = validated.missing_required_fields or []
            
            raise ValidationEnforcementError(
                message=f"Validation failed: {', '.join(issues)}",
                verification_issues=list(issues),
                missing_required_fields=list(missing),
                receipt_id=receipt_id,
            )
        
        return validated

    def to_contract_result(
        self,
        result: ExtractionResult,
        target_id: Optional[str] = None,
        validator_name: str = "ValidationService",
    ) -> ValidationResult:
        """Convert ExtractionResult validation state to Phase 12 ValidationResult contract.
        
        Phase 12A-4 Integration: This method bridges the ExtractionResult-based
        validation with the Phase 12 contract system, enabling interoperability
        with other 12A components.
        
        Args:
            result: ExtractionResult (should be pre-validated via validate())
            target_id: Optional target ID for the validation result (e.g., draft_id)
            validator_name: Name identifying this validator (default: "ValidationService")
            
        Returns:
            ValidationResult contract type with mapped issues
        """
        issues: List[ValidationIssue] = []
        
        # Map verification_issues to ValidationIssue objects
        for issue_code in (result.verification_issues or []):
            # Determine severity based on issue type
            if issue_code.startswith("missing_"):
                severity = ValidationSeverity.ERROR
                message = f"Required field is missing: {issue_code.replace('missing_', '')}"
                field_name = issue_code.replace("missing_", "")
            elif issue_code == "financial_inconsistency":
                severity = ValidationSeverity.WARNING
                message = "Subtotal + tax does not match total within tolerance"
                field_name = "total"
            else:
                severity = ValidationSeverity.WARNING
                message = f"Validation issue: {issue_code}"
                field_name = None
            
            issues.append(ValidationIssue(
                code=issue_code,
                severity=severity,
                message=message,
                field_name=field_name,
            ))
        
        return ValidationResult(
            is_valid=result.verified if result.verified is not None else len(issues) == 0,
            issues=issues,
            validator_name=validator_name,
            target_id=target_id,
        )


__all__ = [
    "ValidationService",
    "ValidationEnforcementError",
    "ENFORCE_VALIDATION",
]
