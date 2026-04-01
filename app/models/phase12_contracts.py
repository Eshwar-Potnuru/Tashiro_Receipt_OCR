"""
Phase 12 Interface Contracts (Phase 9 Step 5 Scaffolding)

This module provides ISOLATED, MINIMAL interface scaffolding to prepare for
future Phase 12A/12B work. These are typed models, enums, and contracts ONLY.

=============================================================================
IMPORTANT - THIS IS NOT:
=============================================================================
- Full Phase 12A implementation
- Full Phase 12B implementation
- Production behavior changes
- Active runtime integration

This scaffolding exists solely to:
1. Define clean interfaces for later implementation
2. Allow type-safe development of Phase 12 features AFTER live PoC passes
3. Provide test stubs for isolated validation
4. Document expected data structures

=============================================================================
PHASE 12A CONCEPTS (Sync-Layer Validation / Access Control / Recovery)
=============================================================================
- Validation result models for sync-layer checks
- Access control decision models
- Recovery operation request/result models

=============================================================================
PHASE 12B CONCEPTS (Excel Change Detection / Sync Checkpoints / Status)
=============================================================================
- External Excel change detection result models
- Sync checkpoint models for tracking reconciliation state
- Status transition models for formalized state changes
- Reconciliation outcome models

=============================================================================
USAGE RESTRICTION
=============================================================================
These models are NOT wired into production flow. They are isolated contracts
for future phase work. Do not import these into active runtime paths until
Phase 10 live PoC is complete and Phase 12 implementation begins.

Author: Phase 9 Step 5 - Limited Interface Scaffolding
Date: 2026-03-21
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict
from uuid import UUID


# =============================================================================
# PHASE 12A: VALIDATION CONTRACTS
# =============================================================================

class ValidationSeverity(str, Enum):
    """Severity levels for validation issues.
    
    Used by sync-layer validation to categorize issues found during
    pre-write or post-write checks.
    """
    INFO = "INFO"
    """Informational - does not block operation."""
    
    WARNING = "WARNING"
    """Warning - operation proceeds but should be reviewed."""
    
    ERROR = "ERROR"
    """Error - operation blocked, requires correction."""
    
    CRITICAL = "CRITICAL"
    """Critical - system-level issue, requires immediate attention."""


@dataclass
class ValidationIssue:
    """Single validation issue found during sync-layer checks.
    
    Attributes:
        code: Machine-readable issue code (e.g., "MISSING_FIELD", "INVALID_DATE")
        severity: Issue severity level
        message: Human-readable description
        field_name: Field that caused the issue (if applicable)
        context: Additional context for debugging
    """
    code: str
    severity: ValidationSeverity
    message: str
    field_name: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class ValidationResult:
    """Result of sync-layer validation checks.
    
    Used to capture validation outcomes before or after Excel operations.
    Provides structured feedback for debugging and compliance.
    
    Attributes:
        is_valid: True if no blocking errors were found
        issues: List of validation issues discovered
        checked_at: Timestamp when validation was performed
        validator_name: Name of the validator that ran
        target_id: ID of the entity being validated (draft_id, file_id, etc.)
    
    Example:
        >>> result = ValidationResult(
        ...     is_valid=False,
        ...     issues=[ValidationIssue(
        ...         code="MISSING_FIELD",
        ...         severity=ValidationSeverity.ERROR,
        ...         message="receipt_date is required",
        ...         field_name="receipt_date"
        ...     )],
        ...     validator_name="pre_send_validator",
        ...     target_id="draft-123"
        ... )
    """
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)
    validator_name: Optional[str] = None
    target_id: Optional[str] = None
    
    @property
    def error_count(self) -> int:
        """Count of ERROR or CRITICAL issues."""
        return sum(
            1 for i in self.issues 
            if i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
        )
    
    @property
    def warning_count(self) -> int:
        """Count of WARNING issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)


# =============================================================================
# PHASE 12A: ACCESS CONTROL CONTRACTS
# =============================================================================

class AccessDecision(str, Enum):
    """Access control decision outcomes.
    
    Used by access control checks to communicate decisions.
    """
    ALLOW = "ALLOW"
    """Operation is permitted."""
    
    DENY = "DENY"
    """Operation is denied - user lacks permission."""
    
    REQUIRE_ELEVATION = "REQUIRE_ELEVATION"
    """Operation requires higher privileges (e.g., ADMIN approval)."""
    
    DEFER = "DEFER"
    """Decision cannot be made - defer to another authority."""


@dataclass
class AccessControlDecision:
    """Result of an access control check.
    
    Captures whether an operation is permitted for a given actor/resource.
    
    Attributes:
        decision: The access control outcome
        actor_id: User or system making the request
        resource_type: Type of resource being accessed (e.g., "draft", "excel_file")
        resource_id: ID of the specific resource
        operation: Operation being attempted (e.g., "edit", "delete", "send")
        reason: Human-readable explanation of the decision
        checked_at: Timestamp when check was performed
    
    Example:
        >>> decision = AccessControlDecision(
        ...     decision=AccessDecision.DENY,
        ...     actor_id="user-456",
        ...     resource_type="draft",
        ...     resource_id="draft-123",
        ...     operation="delete",
        ...     reason="SENT drafts cannot be deleted"
        ... )
    """
    decision: AccessDecision
    actor_id: str
    resource_type: str
    resource_id: str
    operation: str
    reason: Optional[str] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_allowed(self) -> bool:
        """Convenience check for ALLOW decision."""
        return self.decision == AccessDecision.ALLOW


# =============================================================================
# PHASE 12A: RECOVERY CONTRACTS
# =============================================================================

class RecoveryOperationType(str, Enum):
    """Types of recovery operations.
    
    Used to categorize what kind of recovery is being requested.
    """
    RETRY_SEND = "RETRY_SEND"
    """Retry a failed send operation."""
    
    REVERT_DRAFT = "REVERT_DRAFT"
    """Revert a draft to previous state."""
    
    RESYNC_FROM_EXCEL = "RESYNC_FROM_EXCEL"
    """Resynchronize draft from Excel authority."""
    
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    """Manual administrative override."""


@dataclass
class RecoveryOperationRequest:
    """Request for a recovery operation.
    
    Captures what recovery is being requested and by whom.
    
    Attributes:
        operation_type: Type of recovery being requested
        target_id: ID of the entity to recover (draft_id, etc.)
        requested_by: User ID requesting the recovery
        reason: Why the recovery is needed
        metadata: Additional operation-specific data
    """
    operation_type: RecoveryOperationType
    target_id: str
    requested_by: str
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RecoveryOutcome(str, Enum):
    """Outcomes of recovery operations."""
    SUCCESS = "SUCCESS"
    """Recovery completed successfully."""
    
    PARTIAL = "PARTIAL"
    """Recovery partially completed - some issues remain."""
    
    FAILED = "FAILED"
    """Recovery failed."""
    
    CANCELLED = "CANCELLED"
    """Recovery was cancelled."""


@dataclass
class RecoveryOperationResult:
    """Result of a recovery operation.
    
    Attributes:
        request: The original recovery request
        outcome: How the recovery concluded
        message: Human-readable result description
        recovered_state: State after recovery (if applicable)
        completed_at: Timestamp when recovery finished
    """
    request: RecoveryOperationRequest
    outcome: RecoveryOutcome
    message: Optional[str] = None
    recovered_state: Optional[Dict[str, Any]] = None
    completed_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# PHASE 12B: SYNC CHECKPOINT CONTRACTS
# =============================================================================

class SyncDirection(str, Enum):
    """Direction of synchronization."""
    APP_TO_EXCEL = "APP_TO_EXCEL"
    """App pushes changes to Excel."""
    
    EXCEL_TO_APP = "EXCEL_TO_APP"
    """Excel changes pulled to app."""
    
    BIDIRECTIONAL = "BIDIRECTIONAL"
    """Both directions checked."""


@dataclass
class SyncCheckpoint:
    """Checkpoint for tracking synchronization state.
    
    Used to record when and what was last synchronized, enabling
    efficient incremental sync operations.
    
    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        file_id: OneDrive file ID being tracked
        worksheet_name: Worksheet being tracked (if applicable)
        last_synced_at: Timestamp of last successful sync
        last_etag: ETag at time of last sync
        last_row_hash: Hash of row data at last sync
        sync_direction: Direction of last sync
        metadata: Additional tracking data
    
    Example:
        >>> checkpoint = SyncCheckpoint(
        ...     checkpoint_id="cp-001",
        ...     file_id="abc123...",
        ...     worksheet_name="2026年3月",
        ...     last_synced_at=datetime.utcnow(),
        ...     last_etag="W/\"abc...\"",
        ...     sync_direction=SyncDirection.APP_TO_EXCEL
        ... )
    """
    checkpoint_id: str
    file_id: str
    worksheet_name: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_etag: Optional[str] = None
    last_row_hash: Optional[str] = None
    sync_direction: Optional[SyncDirection] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# PHASE 12B: EXTERNAL CHANGE DETECTION CONTRACTS
# =============================================================================

class ChangeSource(str, Enum):
    """Source of detected changes."""
    APP = "APP"
    """Change originated from this application."""
    
    EXTERNAL_USER = "EXTERNAL_USER"
    """Change made by user via SharePoint/Excel UI."""
    
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"
    """Change made by another system/integration."""
    
    UNKNOWN = "UNKNOWN"
    """Source could not be determined."""


@dataclass
class ExternalChangeResult:
    """Result of detecting external changes to Excel data.
    
    When polling or checking Excel for external modifications, this
    captures what changes were detected.
    
    Attributes:
        file_id: OneDrive file ID checked
        has_changes: True if changes were detected
        change_source: Detected source of changes
        changed_fields: List of fields that changed
        previous_etag: ETag before change
        current_etag: ETag after change
        detected_at: When the change was detected
        row_index: Row affected (if applicable)
    
    Example:
        >>> result = ExternalChangeResult(
        ...     file_id="abc123...",
        ...     has_changes=True,
        ...     change_source=ChangeSource.EXTERNAL_USER,
        ...     changed_fields=["total_amount", "memo"],
        ...     previous_etag="W/\"old...\"",
        ...     current_etag="W/\"new...\""
        ... )
    """
    file_id: str
    has_changes: bool
    change_source: Optional[ChangeSource] = None
    changed_fields: List[str] = field(default_factory=list)
    previous_etag: Optional[str] = None
    current_etag: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    row_index: Optional[int] = None


# =============================================================================
# PHASE 12B: STATUS TRANSITION CONTRACTS
# =============================================================================

@dataclass
class StatusTransition:
    """Record of a status transition.
    
    Formalizes the state machine transitions for drafts and other entities.
    
    Attributes:
        entity_type: Type of entity (e.g., "draft", "sync_job")
        entity_id: ID of the entity
        from_status: Previous status
        to_status: New status
        triggered_by: What caused the transition (user_id, "SYSTEM", event, etc.)
        transition_time: When the transition occurred
        reason: Why the transition happened
        metadata: Additional transition data
    
    Example:
        >>> transition = StatusTransition(
        ...     entity_type="draft",
        ...     entity_id="draft-123",
        ...     from_status="DRAFT",
        ...     to_status="SENT",
        ...     triggered_by="user-456",
        ...     reason="bulk_send_operation"
        ... )
    """
    entity_type: str
    entity_id: str
    from_status: str
    to_status: str
    triggered_by: str
    transition_time: datetime = field(default_factory=datetime.utcnow)
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# PHASE 12B: RECONCILIATION OUTCOME CONTRACTS
# =============================================================================

class ReconciliationStrategy(str, Enum):
    """Strategy used for reconciliation."""
    EXCEL_WINS = "EXCEL_WINS"
    """Excel values take precedence."""
    
    APP_WINS = "APP_WINS"
    """App values take precedence."""
    
    MERGE = "MERGE"
    """Attempt to merge both sets of changes."""
    
    MANUAL = "MANUAL"
    """Require manual resolution."""


class ReconciliationStatus(str, Enum):
    """Status of a reconciliation operation."""
    PENDING = "PENDING"
    """Reconciliation not yet started."""
    
    IN_PROGRESS = "IN_PROGRESS"
    """Reconciliation is running."""
    
    COMPLETED = "COMPLETED"
    """Reconciliation finished successfully."""
    
    FAILED = "FAILED"
    """Reconciliation failed."""
    
    CONFLICT = "CONFLICT"
    """Conflicts detected, manual resolution required."""


@dataclass
class ReconciliationOutcome:
    """Outcome of a reconciliation operation.
    
    Captures the full result of reconciling app state with Excel.
    
    Attributes:
        draft_id: Draft being reconciled
        status: Final status of reconciliation
        strategy_used: Strategy that was applied
        conflicts_found: Number of conflicts detected
        conflicts_resolved: Number of conflicts resolved
        fields_updated: List of fields that were updated
        excel_row_hash: Hash of Excel row after reconciliation
        app_row_hash: Hash of app state after reconciliation
        reconciled_at: When reconciliation completed
        error_message: Error description if failed
    
    Example:
        >>> outcome = ReconciliationOutcome(
        ...     draft_id="draft-123",
        ...     status=ReconciliationStatus.COMPLETED,
        ...     strategy_used=ReconciliationStrategy.EXCEL_WINS,
        ...     conflicts_found=2,
        ...     conflicts_resolved=2,
        ...     fields_updated=["total_amount", "memo"]
        ... )
    """
    draft_id: str
    status: ReconciliationStatus
    strategy_used: Optional[ReconciliationStrategy] = None
    conflicts_found: int = 0
    conflicts_resolved: int = 0
    fields_updated: List[str] = field(default_factory=list)
    excel_row_hash: Optional[str] = None
    app_row_hash: Optional[str] = None
    reconciled_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    
    @property
    def has_unresolved_conflicts(self) -> bool:
        """Check if there are unresolved conflicts."""
        return self.conflicts_found > self.conflicts_resolved


# =============================================================================
# PLACEHOLDER INTERFACES (No-Op - For Future Implementation)
# =============================================================================

class IValidationService:
    """Interface for sync-layer validation service.
    
    PLACEHOLDER - Not implemented until Phase 12A.
    This interface defines the contract for validation services.
    """
    
    def validate_pre_send(self, draft_id: str) -> ValidationResult:
        """Validate draft before sending to Excel.
        
        Args:
            draft_id: ID of the draft to validate
            
        Returns:
            Validation result with any issues found
            
        Raises:
            NotImplementedError: Until Phase 12A implementation
        """
        raise NotImplementedError("Phase 12A: validate_pre_send not yet implemented")
    
    def validate_post_send(self, draft_id: str, excel_result: Dict[str, Any]) -> ValidationResult:
        """Validate after Excel write to ensure consistency.
        
        Args:
            draft_id: ID of the draft that was sent
            excel_result: Result from Excel write operation
            
        Returns:
            Validation result with any issues found
            
        Raises:
            NotImplementedError: Until Phase 12A implementation
        """
        raise NotImplementedError("Phase 12A: validate_post_send not yet implemented")


class IAccessControlService:
    """Interface for access control service.
    
    PLACEHOLDER - Not implemented until Phase 12A.
    This interface defines the contract for access control decisions.
    """
    
    def check_access(
        self, 
        actor_id: str, 
        resource_type: str, 
        resource_id: str, 
        operation: str
    ) -> AccessControlDecision:
        """Check if an operation is permitted.
        
        Args:
            actor_id: User or system making the request
            resource_type: Type of resource (e.g., "draft", "excel_file")
            resource_id: ID of the specific resource
            operation: Operation being attempted
            
        Returns:
            Access control decision
            
        Raises:
            NotImplementedError: Until Phase 12A implementation
        """
        raise NotImplementedError("Phase 12A: check_access not yet implemented")


class ISyncCheckpointService:
    """Interface for sync checkpoint management.
    
    PLACEHOLDER - Not implemented until Phase 12B.
    This interface defines the contract for tracking sync state.
    """
    
    def get_checkpoint(self, file_id: str) -> Optional[SyncCheckpoint]:
        """Get the current checkpoint for a file.
        
        Args:
            file_id: OneDrive file ID
            
        Returns:
            Current checkpoint or None if not tracked
            
        Raises:
            NotImplementedError: Until Phase 12B implementation
        """
        raise NotImplementedError("Phase 12B: get_checkpoint not yet implemented")
    
    def save_checkpoint(self, checkpoint: SyncCheckpoint) -> None:
        """Save a sync checkpoint.
        
        Args:
            checkpoint: Checkpoint to save
            
        Raises:
            NotImplementedError: Until Phase 12B implementation
        """
        raise NotImplementedError("Phase 12B: save_checkpoint not yet implemented")


class IExternalChangeDetector:
    """Interface for detecting external Excel changes.
    
    PLACEHOLDER - Not implemented until Phase 12B.
    This interface defines the contract for change detection.
    """
    
    def detect_changes(self, file_id: str, since_etag: Optional[str] = None) -> ExternalChangeResult:
        """Detect if external changes occurred since last check.
        
        Args:
            file_id: OneDrive file ID to check
            since_etag: Optional ETag to compare against
            
        Returns:
            Result indicating if changes were detected
            
        Raises:
            NotImplementedError: Until Phase 12B implementation
        """
        raise NotImplementedError("Phase 12B: detect_changes not yet implemented")


# =============================================================================
# TYPE ALIASES FOR CONVENIENCE
# =============================================================================

# Dictionary type for sync status (used in API responses)
SyncStatusDict = TypedDict('SyncStatusDict', {
    'is_synced': bool,
    'last_sync_time': Optional[str],
    'conflicts': List[Dict[str, Any]],
    'etag': Optional[str],
})

# Dictionary type for validation summary
ValidationSummaryDict = TypedDict('ValidationSummaryDict', {
    'is_valid': bool,
    'error_count': int,
    'warning_count': int,
    'issues': List[Dict[str, Any]],
})


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Phase 12A - Validation
    'ValidationSeverity',
    'ValidationIssue', 
    'ValidationResult',
    # Phase 12A - Access Control
    'AccessDecision',
    'AccessControlDecision',
    # Phase 12A - Recovery
    'RecoveryOperationType',
    'RecoveryOperationRequest',
    'RecoveryOutcome',
    'RecoveryOperationResult',
    # Phase 12B - Sync Checkpoints
    'SyncDirection',
    'SyncCheckpoint',
    # Phase 12B - External Changes
    'ChangeSource',
    'ExternalChangeResult',
    # Phase 12B - Status Transitions
    'StatusTransition',
    # Phase 12B - Reconciliation
    'ReconciliationStrategy',
    'ReconciliationStatus',
    'ReconciliationOutcome',
    # Interfaces (Placeholders)
    'IValidationService',
    'IAccessControlService',
    'ISyncCheckpointService',
    'IExternalChangeDetector',
    # Type Aliases
    'SyncStatusDict',
    'ValidationSummaryDict',
]
