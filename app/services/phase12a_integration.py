"""Phase 12A Integration Utilities

Lightweight helpers for coordinating Phase 12A components (validation, access
control, recovery) without broadening scope or changing production behavior.

Phase 12A-4 (Integration Pass):
    - Provides unified result structure for combined checks
    - Enables consistent error/decision semantics across 12A components
    - Does NOT change user-visible behavior
    - Does NOT wire recovery to API endpoints (deferred to later phase)

Important:
    - ENFORCE_VALIDATION defaults to false (advisory mode)
    - USE_GRAPH_API_WRITERS defaults to false (no live Excel writes)
    - Recovery endpoint exposure is intentionally deferred

Author: Phase 12A-4 - Integration Completion
Date: 2026-03-24
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models.phase12_contracts import (
    AccessControlDecision,
    AccessDecision,
    ValidationResult,
    ValidationSeverity,
    RecoveryOperationResult,
    RecoveryOutcome,
)


class Phase12ACheckOutcome(str, Enum):
    """Unified outcome for combined Phase 12A checks.
    
    Used to summarize the overall result of validation + access control + recovery.
    """
    PASSED = "PASSED"
    """All checks passed - operation can proceed."""
    
    ADVISORY_WARNINGS = "ADVISORY_WARNINGS"
    """Operation can proceed, but warnings were generated."""
    
    ACCESS_DENIED = "ACCESS_DENIED"
    """Access control denied the operation."""
    
    VALIDATION_FAILED = "VALIDATION_FAILED"
    """Validation blocked the operation (enforcement mode)."""
    
    RECOVERY_NEEDED = "RECOVERY_NEEDED"
    """State requires recovery before operation can proceed."""
    
    DEFERRED = "DEFERRED"
    """Cannot complete check - requires deferred resources (e.g., Graph API)."""


@dataclass
class Phase12ACheckResult:
    """Unified result for combined Phase 12A checks.
    
    Aggregates outcomes from validation, access control, and recovery checks
    into a single coherent result structure.
    
    Attributes:
        outcome: Overall outcome of the combined checks
        access_decision: Access control decision (if performed)
        validation_result: Validation result (if performed)
        recovery_result: Recovery result (if performed)
        can_proceed: True if the operation can proceed
        messages: Human-readable messages explaining the result
        checked_at: Timestamp when checks were performed
        metadata: Additional context for debugging/auditing
    
    Example:
        >>> from app.services.phase12a_integration import (
        ...     Phase12ACheckResult,
        ...     Phase12ACheckOutcome,
        ... )
        >>> result = Phase12ACheckResult(
        ...     outcome=Phase12ACheckOutcome.PASSED,
        ...     can_proceed=True,
        ...     messages=["All checks passed"],
        ... )
    """
    outcome: Phase12ACheckOutcome
    can_proceed: bool
    access_decision: Optional[AccessControlDecision] = None
    validation_result: Optional[ValidationResult] = None
    recovery_result: Optional[RecoveryOperationResult] = None
    messages: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "outcome": self.outcome.value,
            "can_proceed": self.can_proceed,
            "messages": self.messages,
            "checked_at": self.checked_at.isoformat(),
            "has_access_decision": self.access_decision is not None,
            "has_validation_result": self.validation_result is not None,
            "has_recovery_result": self.recovery_result is not None,
        }


def combine_access_and_validation(
    access_decision: Optional[AccessControlDecision],
    validation_result: Optional[ValidationResult],
    enforce_validation: bool = False,
) -> Phase12ACheckResult:
    """Combine access control and validation results into unified outcome.
    
    This helper coordinates the two main Phase 12A check types for pre-operation
    verification. It does NOT change production behavior - access denial is
    always blocking, validation is advisory unless enforce_validation=True.
    
    Args:
        access_decision: Result of access control check (if performed)
        validation_result: Result of validation check (if performed)
        enforce_validation: If True, validation errors block operation
            (matches ENFORCE_VALIDATION flag behavior)
    
    Returns:
        Phase12ACheckResult with combined outcome
        
    Example:
        >>> from app.services.access_control_service import AccessControlService
        >>> from app.services.validation_service import ValidationService
        >>> 
        >>> # Perform checks
        >>> access = AccessControlService.check_draft_access(user, draft, "send")
        >>> validation = ValidationService().to_contract_result(draft.receipt, str(draft.id))
        >>> 
        >>> # Combine results
        >>> combined = combine_access_and_validation(access, validation, enforce_validation=False)
        >>> if combined.can_proceed:
        ...     proceed_with_operation()
    """
    messages: List[str] = []
    
    # Check access control first (always blocking if denied)
    if access_decision is not None and not access_decision.is_allowed:
        return Phase12ACheckResult(
            outcome=Phase12ACheckOutcome.ACCESS_DENIED,
            can_proceed=False,
            access_decision=access_decision,
            validation_result=validation_result,
            messages=[
                f"Access denied: {access_decision.reason or 'Insufficient permissions'}",
            ],
        )
    
    # Check validation (blocking only if enforce_validation is True)
    if validation_result is not None:
        if not validation_result.is_valid:
            error_count = validation_result.error_count
            warning_count = validation_result.warning_count
            
            if enforce_validation and error_count > 0:
                return Phase12ACheckResult(
                    outcome=Phase12ACheckOutcome.VALIDATION_FAILED,
                    can_proceed=False,
                    access_decision=access_decision,
                    validation_result=validation_result,
                    messages=[
                        f"Validation failed: {error_count} error(s), {warning_count} warning(s)",
                    ],
                )
            elif error_count > 0 or warning_count > 0:
                messages.append(
                    f"Advisory: {error_count} validation error(s), {warning_count} warning(s)"
                )
    
    # All checks passed (or advisory only)
    if messages:
        return Phase12ACheckResult(
            outcome=Phase12ACheckOutcome.ADVISORY_WARNINGS,
            can_proceed=True,
            access_decision=access_decision,
            validation_result=validation_result,
            messages=messages,
        )
    
    return Phase12ACheckResult(
        outcome=Phase12ACheckOutcome.PASSED,
        can_proceed=True,
        access_decision=access_decision,
        validation_result=validation_result,
        messages=["All Phase 12A checks passed"],
    )


def check_recovery_prerequisite(
    recovery_result: Optional[RecoveryOperationResult],
) -> Phase12ACheckResult:
    """Check if recovery operation indicates a blocking state.
    
    This helper checks recovery results to determine if an operation can
    proceed or if recovery must complete first.
    
    Note: This is infrastructure only - recovery API exposure is deferred.
    
    Args:
        recovery_result: Result of a recovery check/operation
        
    Returns:
        Phase12ACheckResult with recovery-based outcome
    """
    if recovery_result is None:
        return Phase12ACheckResult(
            outcome=Phase12ACheckOutcome.PASSED,
            can_proceed=True,
            messages=["No recovery required"],
        )
    
    if recovery_result.outcome == RecoveryOutcome.SUCCESS:
        return Phase12ACheckResult(
            outcome=Phase12ACheckOutcome.PASSED,
            can_proceed=True,
            recovery_result=recovery_result,
            messages=[recovery_result.message or "Recovery completed successfully"],
        )
    
    if recovery_result.outcome == RecoveryOutcome.PARTIAL:
        return Phase12ACheckResult(
            outcome=Phase12ACheckOutcome.ADVISORY_WARNINGS,
            can_proceed=True,
            recovery_result=recovery_result,
            messages=[
                recovery_result.message or "Recovery partially completed - review required"
            ],
        )
    
    # Failed or deferred recovery
    is_deferred = "deferred" in (recovery_result.message or "").lower()
    
    if is_deferred:
        return Phase12ACheckResult(
            outcome=Phase12ACheckOutcome.DEFERRED,
            can_proceed=False,
            recovery_result=recovery_result,
            messages=[
                recovery_result.message or "Recovery requires Graph API (deferred)"
            ],
        )
    
    return Phase12ACheckResult(
        outcome=Phase12ACheckOutcome.RECOVERY_NEEDED,
        can_proceed=False,
        recovery_result=recovery_result,
        messages=[recovery_result.message or "Recovery failed - cannot proceed"],
    )


def is_phase12a_safe_mode() -> bool:
    """Check if Phase 12A is running in safe mode (defaults preserved).
    
    Safe mode means:
    - ENFORCE_VALIDATION is false (advisory validation only)
    - USE_GRAPH_API_WRITERS is false (no live Excel writes)
    
    This is useful for verifying production defaults are preserved.
    
    Returns:
        True if both safety flags have safe defaults
    """
    import os
    
    enforce_validation = os.environ.get("ENFORCE_VALIDATION", "false").lower() in (
        "1", "true", "yes"
    )
    use_graph_writers = os.environ.get("USE_GRAPH_API_WRITERS", "false").lower() in (
        "1", "true", "yes"
    )
    
    return not enforce_validation and not use_graph_writers


__all__ = [
    "Phase12ACheckOutcome",
    "Phase12ACheckResult",
    "combine_access_and_validation",
    "check_recovery_prerequisite",
    "is_phase12a_safe_mode",
]
