"""
Phase 12B-3: Sync Reconciliation Integration Service

This is the INTEGRATION LAYER that ties together all Phase 12B components:
    - SyncCheckpointService (Phase 12B-2): Checkpoint storage
    - ExternalChangeDetectorService (Phase 12B-2): Change detection
    - ExcelReconciliationService (Phase 11B): Consistency checking
    - StatusWorkflowService (Phase 12B-1): Status mapping and transitions

Purpose:
    Provide a unified reconciliation workflow that answers:
    1. Has external source changed since last checkpoint?
    2. Does local state match known external state?
    3. Is result consistent, externally changed, conflicting, or unknown?
    4. What user-facing status should remain visible?
    5. What internal follow-up should be recorded?

Design Principles:
    - NO live Graph API calls (all values must be provided)
    - NO polling daemon (this is an internal integration layer)
    - Production behavior UNCHANGED
    - USE_GRAPH_API_WRITERS default remains false
    - ENFORCE_VALIDATION default remains false

Usage:
    from app.services.sync_reconciliation_service import (
        SyncReconciliationService,
        get_sync_reconciliation_service,
        SyncReconciliationResult,
    )
    
    service = get_sync_reconciliation_service()
    
    # Full reconciliation with external values
    result = service.reconcile_draft(
        draft=my_draft,
        current_excel_values=excel_row_dict,
        current_etag="W/\"abc...\"",
        current_hash="sha256sum...",
    )
    
    if result.needs_resolution:
        # Handle conflict
        print(f"Conflict: {result.consistency_result.status}")
    
    # Create checkpoint after successful send
    service.create_post_send_checkpoint(
        draft=my_draft,
        file_id="onedrive-file-id",
        worksheet_name="2026年3月",
        etag="W/\"abc...\"",
        row_hash="sha256sum...",
    )

Author: Phase 12B-3 Integration
Date: 2026-03-28
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.models.draft import DraftReceipt, DraftStatus
from app.models.phase12_contracts import (
    SyncCheckpoint,
    SyncDirection,
    ReconciliationStatus,
    ReconciliationStrategy,
    ReconciliationOutcome,
)
from app.services.sync_checkpoint_service import (
    SyncCheckpointService,
    get_sync_checkpoint_service,
    compute_checkpoint_hash,
)
from app.services.external_change_detector_service import (
    ExternalChangeDetectorService,
    ChangeDetectionOutcome,
    ChangeDetectionResult,
    get_external_change_detector,
)
from app.services.excel_reconciliation import (
    ExcelReconciliationService,
    ConsistencyStatus,
    ConsistencyCheckResult,
    ConflictSeverity,
    get_excel_reconciliation_service,
)
from app.services.status_workflow_service import (
    StatusWorkflowService,
    UserFacingStatus,
    get_user_facing_status,
    get_status_workflow_service,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SYNC RECONCILIATION OUTCOME ENUM
# =============================================================================

class SyncReconciliationOutcome(str, Enum):
    """High-level outcome of sync reconciliation.
    
    Provides a simplified summary of the reconciliation result.
    
    Attributes:
        SYNCHRONIZED: Draft and Excel are in sync, no action needed
        LOCAL_ONLY_CHANGE: Draft changed locally, Excel unchanged
        EXTERNAL_ONLY_CHANGE: Excel changed externally, draft unchanged
        CONFLICT_DETECTED: Both changed, manual resolution needed
        INSUFFICIENT_DATA: Cannot determine (missing checkpoints/values)
        NO_BASELINE: No checkpoint exists, treat as first sync
        ERROR: Error during reconciliation
    """
    SYNCHRONIZED = "SYNCHRONIZED"
    LOCAL_ONLY_CHANGE = "LOCAL_ONLY_CHANGE"
    EXTERNAL_ONLY_CHANGE = "EXTERNAL_ONLY_CHANGE"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_BASELINE = "NO_BASELINE"
    ERROR = "ERROR"


# =============================================================================
# SYNC RECONCILIATION RESULT
# =============================================================================

@dataclass
class SyncReconciliationResult:
    """Complete result of sync reconciliation analysis.
    
    Combines results from all integrated services into a unified response.
    
    Attributes:
        draft_id: ID of the draft being reconciled
        outcome: High-level reconciliation outcome
        consistency_result: Detailed consistency check result
        change_detection_result: External change detection result
        user_facing_status: Current user-facing status
        internal_status: Current internal DraftStatus
        needs_resolution: True if manual resolution is required
        can_sync_safely: True if sync can proceed without conflicts
        recommended_action: Suggested next step
        reconciled_at: Timestamp of this reconciliation
        details: Additional diagnostic information
    """
    draft_id: str
    outcome: SyncReconciliationOutcome
    consistency_result: Optional[ConsistencyCheckResult] = None
    change_detection_result: Optional[ChangeDetectionResult] = None
    user_facing_status: Optional[UserFacingStatus] = None
    internal_status: Optional[DraftStatus] = None
    needs_resolution: bool = False
    can_sync_safely: bool = True
    recommended_action: Optional[str] = None
    reconciled_at: datetime = field(default_factory=datetime.utcnow)
    details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "draft_id": self.draft_id,
            "outcome": self.outcome.value,
            "user_facing_status": self.user_facing_status.value if self.user_facing_status else None,
            "internal_status": self.internal_status.value if self.internal_status else None,
            "needs_resolution": self.needs_resolution,
            "can_sync_safely": self.can_sync_safely,
            "recommended_action": self.recommended_action,
            "reconciled_at": self.reconciled_at.isoformat(),
            "details": self.details,
        }
        
        if self.consistency_result:
            result["consistency"] = self.consistency_result.to_dict()
        
        if self.change_detection_result:
            result["change_detection"] = self.change_detection_result.to_dict()
        
        return result
    
    @property
    def has_conflict(self) -> bool:
        """True if a conflict was detected."""
        return self.outcome == SyncReconciliationOutcome.CONFLICT_DETECTED
    
    @property
    def has_external_change(self) -> bool:
        """True if external change was detected."""
        return self.outcome in (
            SyncReconciliationOutcome.EXTERNAL_ONLY_CHANGE,
            SyncReconciliationOutcome.CONFLICT_DETECTED,
        )
    
    @property
    def has_local_change(self) -> bool:
        """True if local change was detected."""
        return self.outcome in (
            SyncReconciliationOutcome.LOCAL_ONLY_CHANGE,
            SyncReconciliationOutcome.CONFLICT_DETECTED,
        )
    
    @property
    def is_conclusive(self) -> bool:
        """True if reconciliation produced a definitive outcome."""
        return self.outcome not in (
            SyncReconciliationOutcome.INSUFFICIENT_DATA,
            SyncReconciliationOutcome.NO_BASELINE,
            SyncReconciliationOutcome.ERROR,
        )


# =============================================================================
# CHECKPOINT CREATION RESULT
# =============================================================================

@dataclass
class CheckpointCreationResult:
    """Result of creating a sync checkpoint.
    
    Attributes:
        success: True if checkpoint was created successfully
        checkpoint_key: Key used to store the checkpoint
        file_id: OneDrive file ID
        etag: ETag stored in checkpoint
        row_hash: Row hash stored in checkpoint
        created_at: When checkpoint was created
        error_message: Error description if failed
    """
    success: bool
    checkpoint_key: Optional[str] = None
    file_id: Optional[str] = None
    etag: Optional[str] = None
    row_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "checkpoint_key": self.checkpoint_key,
            "file_id": self.file_id,
            "etag": self.etag,
            "row_hash": self.row_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "error_message": self.error_message,
        }


# =============================================================================
# SYNC RECONCILIATION SERVICE
# =============================================================================

class SyncReconciliationService:
    """
    Integration service that unifies sync/reconciliation components.
    
    This service integrates:
        - SyncCheckpointService: Checkpoint management
        - ExternalChangeDetectorService: Change detection
        - ExcelReconciliationService: Consistency checking
        - StatusWorkflowService: Status mapping
    
    Key responsibilities:
        1. Orchestrate reconciliation workflow
        2. Combine component results into unified outcome
        3. Provide clear action recommendations
        4. Manage checkpoint lifecycle
    
    Thread Safety:
        - This service is stateless beyond service references
        - Component services handle their own thread safety
    
    Example:
        >>> service = SyncReconciliationService()
        >>> result = service.reconcile_draft(draft, excel_values={"total_amount": "1000"})
        >>> if result.needs_resolution:
        ...     print(f"Conflict detected: {result.outcome}")
    """
    
    def __init__(
        self,
        checkpoint_service: Optional[SyncCheckpointService] = None,
        change_detector: Optional[ExternalChangeDetectorService] = None,
        reconciliation_service: Optional[ExcelReconciliationService] = None,
        status_workflow: Optional[StatusWorkflowService] = None,
    ):
        """
        Initialize the integration service.
        
        Args:
            checkpoint_service: Optional checkpoint service (uses singleton if None)
            change_detector: Optional change detector (uses singleton if None)
            reconciliation_service: Optional reconciliation service (uses singleton if None)
            status_workflow: Optional status workflow service (uses singleton if None)
        """
        self._checkpoint_service = checkpoint_service or get_sync_checkpoint_service()
        self._change_detector = change_detector or get_external_change_detector()
        self._reconciliation_service = reconciliation_service or get_excel_reconciliation_service()
        self._status_workflow = status_workflow or get_status_workflow_service()
        
        # Statistics
        self._reconciliation_count = 0
        self._conflict_count = 0
        self._checkpoint_count = 0
        
        logger.info("SyncReconciliationService initialized with all components")
    
    # -------------------------------------------------------------------------
    # CORE RECONCILIATION API
    # -------------------------------------------------------------------------
    
    def reconcile_draft(
        self,
        draft: DraftReceipt,
        current_excel_values: Optional[Dict[str, Any]] = None,
        current_etag: Optional[str] = None,
        current_hash: Optional[str] = None,
        file_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
    ) -> SyncReconciliationResult:
        """
        Perform full reconciliation analysis for a draft.
        
        This is the main entry point for reconciliation. It:
        1. Checks draft consistency (local vs baseline)
        2. Detects external changes (if checkpoint exists)
        3. Combines results into unified outcome
        4. Provides action recommendations
        
        Args:
            draft: The DraftReceipt to reconcile
            current_excel_values: Current row values from Excel (if available)
            current_etag: Current file ETag from Graph API (if available)
            current_hash: Pre-computed hash of Excel row (if available)
            file_id: OneDrive file ID (uses draft.format1_file_id if None)
            worksheet_name: Worksheet name (uses draft.format1_worksheet_name if None)
            
        Returns:
            SyncReconciliationResult with comprehensive analysis
        """
        self._reconciliation_count += 1
        draft_id = str(draft.draft_id)
        
        try:
            # Get current status
            internal_status = draft.status
            user_facing = get_user_facing_status(internal_status)
            
            # Determine file_id from draft if not provided
            effective_file_id = file_id or getattr(draft, 'format1_file_id', None)
            effective_worksheet = worksheet_name or getattr(draft, 'format1_worksheet_name', None)
            
            # Step 1: Check draft consistency (local vs baseline)
            consistency_result = self._reconciliation_service.check_draft_consistency(
                draft=draft,
                excel_values=current_excel_values,
            )
            
            # Step 2: Detect external changes (if we have checkpoint data)
            change_result: Optional[ChangeDetectionResult] = None
            if effective_file_id and (current_etag or current_hash):
                change_result = self._change_detector.detect_changes_with_values(
                    file_id=effective_file_id,
                    worksheet_name=effective_worksheet,
                    current_etag=current_etag,
                    current_hash=current_hash,
                    current_row_values=current_excel_values,
                )
            
            # Step 3: Combine results into unified outcome
            outcome, needs_resolution, can_sync, recommended = self._determine_outcome(
                consistency_result=consistency_result,
                change_result=change_result,
                internal_status=internal_status,
            )
            
            if outcome == SyncReconciliationOutcome.CONFLICT_DETECTED:
                self._conflict_count += 1
            
            return SyncReconciliationResult(
                draft_id=draft_id,
                outcome=outcome,
                consistency_result=consistency_result,
                change_detection_result=change_result,
                user_facing_status=user_facing,
                internal_status=internal_status,
                needs_resolution=needs_resolution,
                can_sync_safely=can_sync,
                recommended_action=recommended,
            )
            
        except Exception as e:
            logger.error(f"Reconciliation error for draft {draft_id}: {e}")
            return SyncReconciliationResult(
                draft_id=draft_id,
                outcome=SyncReconciliationOutcome.ERROR,
                needs_resolution=False,
                can_sync_safely=False,
                recommended_action="Review error and retry",
                details=str(e),
            )
    
    def reconcile_draft_quick(
        self,
        draft: DraftReceipt,
    ) -> SyncReconciliationResult:
        """
        Perform quick reconciliation without external values.
        
        Uses only local state (draft, pre_edit_snapshot, excel_last_known_values)
        to determine consistency. Cannot detect live external changes.
        
        Args:
            draft: The DraftReceipt to check
            
        Returns:
            SyncReconciliationResult based on local state only
        """
        return self.reconcile_draft(draft=draft)
    
    # -------------------------------------------------------------------------
    # CHECKPOINT MANAGEMENT
    # -------------------------------------------------------------------------
    
    def create_post_send_checkpoint(
        self,
        draft: DraftReceipt,
        file_id: str,
        worksheet_name: Optional[str] = None,
        etag: Optional[str] = None,
        row_hash: Optional[str] = None,
        row_values: Optional[Dict[str, Any]] = None,
    ) -> CheckpointCreationResult:
        """
        Create a checkpoint after successful send operation.
        
        Should be called after draft is successfully written to Excel
        to establish the baseline for future reconciliation.
        
        Args:
            draft: The sent DraftReceipt
            file_id: OneDrive file ID where row was written
            worksheet_name: Worksheet name
            etag: Current file ETag after write
            row_hash: Hash of the written row (computed if row_values provided)
            row_values: Row values (used to compute hash if row_hash not provided)
            
        Returns:
            CheckpointCreationResult indicating success/failure
        """
        self._checkpoint_count += 1
        
        try:
            # Compute hash from values if not provided
            effective_hash = row_hash
            if not effective_hash and row_values:
                effective_hash = compute_checkpoint_hash(row_values)
            
            # Create checkpoint
            checkpoint = SyncCheckpoint(
                checkpoint_id=f"cp-{draft.draft_id}",
                file_id=file_id,
                worksheet_name=worksheet_name,
                last_synced_at=datetime.utcnow(),
                last_etag=etag,
                last_row_hash=effective_hash,
                sync_direction=SyncDirection.APP_TO_EXCEL,
                metadata={
                    "draft_id": str(draft.draft_id),
                    "internal_status": draft.status.value,
                },
            )
            
            # Generate checkpoint key
            checkpoint_key = self._checkpoint_service.make_checkpoint_key(
                file_id=file_id,
                worksheet_name=worksheet_name,
            )
            
            # Save checkpoint
            self._checkpoint_service.save_checkpoint(checkpoint)
            
            logger.info(f"Created post-send checkpoint for draft {draft.draft_id}: {checkpoint_key}")
            
            return CheckpointCreationResult(
                success=True,
                checkpoint_key=checkpoint_key,
                file_id=file_id,
                etag=etag,
                row_hash=effective_hash,
                created_at=checkpoint.last_synced_at,
            )
            
        except Exception as e:
            logger.error(f"Failed to create checkpoint for draft {draft.draft_id}: {e}")
            return CheckpointCreationResult(
                success=False,
                error_message=str(e),
            )
    
    def update_checkpoint_after_resolution(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        new_etag: Optional[str] = None,
        new_hash: Optional[str] = None,
        sync_direction: SyncDirection = SyncDirection.EXCEL_TO_APP,
    ) -> CheckpointCreationResult:
        """
        Update checkpoint after conflict resolution.
        
        Called after a conflict is resolved (e.g., Excel wins) to 
        update the checkpoint baseline.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Worksheet name
            new_etag: New ETag after resolution
            new_hash: New row hash after resolution
            sync_direction: Direction of sync that resolved conflict
            
        Returns:
            CheckpointCreationResult indicating success/failure
        """
        try:
            existing = self._checkpoint_service.get_checkpoint_for_file(
                file_id=file_id,
                worksheet_name=worksheet_name,
            )
            
            if existing:
                # Update existing checkpoint
                existing.last_etag = new_etag or existing.last_etag
                existing.last_row_hash = new_hash or existing.last_row_hash
                existing.last_synced_at = datetime.utcnow()
                existing.sync_direction = sync_direction
                
                self._checkpoint_service.save_checkpoint(existing)
                
                return CheckpointCreationResult(
                    success=True,
                    checkpoint_key=existing.checkpoint_id,
                    file_id=file_id,
                    etag=existing.last_etag,
                    row_hash=existing.last_row_hash,
                    created_at=existing.last_synced_at,
                )
            else:
                # Create new checkpoint
                checkpoint = SyncCheckpoint(
                    checkpoint_id=f"cp-{file_id[:8]}-resolved",
                    file_id=file_id,
                    worksheet_name=worksheet_name,
                    last_synced_at=datetime.utcnow(),
                    last_etag=new_etag,
                    last_row_hash=new_hash,
                    sync_direction=sync_direction,
                )
                
                self._checkpoint_service.save_checkpoint(checkpoint)
                
                return CheckpointCreationResult(
                    success=True,
                    checkpoint_key=checkpoint.checkpoint_id,
                    file_id=file_id,
                    etag=new_etag,
                    row_hash=new_hash,
                    created_at=checkpoint.last_synced_at,
                )
                
        except Exception as e:
            logger.error(f"Failed to update checkpoint for {file_id}: {e}")
            return CheckpointCreationResult(
                success=False,
                error_message=str(e),
            )
    
    # -------------------------------------------------------------------------
    # STATUS INTEGRATION
    # -------------------------------------------------------------------------
    
    def get_reconciliation_status_summary(
        self,
        draft: DraftReceipt,
    ) -> Dict[str, Any]:
        """
        Get a summary of draft status for UI display.
        
        Combines internal status, user-facing status, and reconciliation
        state into a unified summary for UI consumption.
        
        Args:
            draft: The DraftReceipt to summarize
            
        Returns:
            Dictionary with status summary
        """
        internal_status = draft.status
        user_facing = get_user_facing_status(internal_status)
        
        # Check for conflict flag
        has_conflict_flag = getattr(draft, 'excel_conflict_detected', False)
        
        # Quick consistency check (no external calls)
        consistency = self._reconciliation_service.check_draft_consistency(draft)
        
        return {
            "draft_id": str(draft.draft_id),
            "internal_status": internal_status.value,
            "user_facing_status": user_facing.value,
            "user_facing_display": user_facing.value,
            "has_conflict_flag": has_conflict_flag,
            "consistency_status": consistency.status.value,
            "consistency_severity": consistency.severity.value,
            "has_local_changes": consistency.has_local_changes,
            "has_external_changes": consistency.has_external_changes,
            "checked_at": datetime.utcnow().isoformat(),
        }
    
    def record_reconciliation_transition(
        self,
        draft: DraftReceipt,
        from_status: DraftStatus,
        to_status: DraftStatus,
        triggered_by: str,
        reason: str,
        reconciliation_result: Optional[SyncReconciliationResult] = None,
    ) -> bool:
        """
        Record a status transition during reconciliation.
        
        Uses StatusWorkflowService to record transitions that occur
        as part of the reconciliation workflow.
        
        Args:
            draft: The DraftReceipt being transitioned
            from_status: Previous status
            to_status: New status
            triggered_by: User ID or "SYSTEM"
            reason: Reason for transition
            reconciliation_result: Optional reconciliation result for context
            
        Returns:
            True if transition was recorded successfully
        """
        try:
            # Build metadata
            metadata = {
                "component": "sync_reconciliation_service",
            }
            
            if reconciliation_result:
                metadata["reconciliation_outcome"] = reconciliation_result.outcome.value
                metadata["had_conflict"] = reconciliation_result.has_conflict
            
            # Record transition
            record = self._status_workflow.record_transition(
                draft_id=str(draft.draft_id),
                from_status=from_status,
                to_status=to_status,
                triggered_by=triggered_by,
                reason=reason,
                metadata=metadata,
            )
            
            logger.info(
                f"Recorded reconciliation transition for {draft.draft_id}: "
                f"{from_status.value} -> {to_status.value}"
            )
            
            return record is not None
            
        except Exception as e:
            logger.error(f"Failed to record transition for {draft.draft_id}: {e}")
            return False
    
    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------
    
    def _determine_outcome(
        self,
        consistency_result: ConsistencyCheckResult,
        change_result: Optional[ChangeDetectionResult],
        internal_status: DraftStatus,
    ) -> Tuple[SyncReconciliationOutcome, bool, bool, str]:
        """
        Determine unified outcome from component results.
        
        Args:
            consistency_result: Result from ExcelReconciliationService
            change_result: Result from ExternalChangeDetectorService (may be None)
            internal_status: Current internal status
            
        Returns:
            Tuple of (outcome, needs_resolution, can_sync_safely, recommended_action)
        """
        # Check for insufficient data
        if consistency_result.status == ConsistencyStatus.UNKNOWN:
            if not consistency_result.has_baseline and not consistency_result.has_excel_baseline:
                return (
                    SyncReconciliationOutcome.NO_BASELINE,
                    False,
                    True,  # Can sync, will establish baseline
                    "Proceed with sync to establish baseline",
                )
            return (
                SyncReconciliationOutcome.INSUFFICIENT_DATA,
                False,
                False,
                "Cannot determine status - review draft metadata",
            )
        
        # Check for conflict
        if consistency_result.status == ConsistencyStatus.CONFLICT:
            return (
                SyncReconciliationOutcome.CONFLICT_DETECTED,
                True,  # Needs resolution
                False,  # Cannot sync safely
                "Resolve conflict before syncing - choose Excel wins or App wins",
            )
        
        # Check for external-only change
        if consistency_result.status == ConsistencyStatus.EXTERNAL_CHANGE:
            return (
                SyncReconciliationOutcome.EXTERNAL_ONLY_CHANGE,
                True,  # Needs resolution (user must decide)
                False,  # Cannot sync without decision
                "External change detected - review and accept or reject changes",
            )
        
        # Check for local-only change
        if consistency_result.status == ConsistencyStatus.LOCAL_CHANGE:
            return (
                SyncReconciliationOutcome.LOCAL_ONLY_CHANGE,
                False,  # No immediate resolution needed
                True,  # Can sync (push local changes)
                "Local changes ready to sync to Excel",
            )
        
        # Check change detection result for additional context
        if change_result and change_result.has_changes:
            # Change detector found changes not reflected in consistency
            # This can happen if we have newer external changes
            if consistency_result.status == ConsistencyStatus.CONSISTENT:
                # Consistency says OK but detector found changes
                # This means checkpoint is stale
                return (
                    SyncReconciliationOutcome.EXTERNAL_ONLY_CHANGE,
                    True,
                    False,
                    "External change detected via checkpoint - review changes",
                )
        
        # If we get here with CONSISTENT status, we're all good
        if consistency_result.status == ConsistencyStatus.CONSISTENT:
            return (
                SyncReconciliationOutcome.SYNCHRONIZED,
                False,  # No resolution needed
                True,  # Safe to sync (no-op)
                "Draft is synchronized with Excel",
            )
        
        # Fallback for unexpected states
        return (
            SyncReconciliationOutcome.INSUFFICIENT_DATA,
            False,
            False,
            "Unable to determine sync status",
        )
    
    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "reconciliation_count": self._reconciliation_count,
            "conflict_count": self._conflict_count,
            "checkpoint_count": self._checkpoint_count,
            "conflict_rate": (
                self._conflict_count / self._reconciliation_count
                if self._reconciliation_count > 0 else 0
            ),
        }


# =============================================================================
# SINGLETON FACTORY
# =============================================================================

_default_service: Optional[SyncReconciliationService] = None


def get_sync_reconciliation_service() -> SyncReconciliationService:
    """
    Get the default SyncReconciliationService singleton.
    
    Returns:
        The default SyncReconciliationService instance
    """
    global _default_service
    if _default_service is None:
        _default_service = SyncReconciliationService()
    return _default_service


def reset_sync_reconciliation_service() -> None:
    """Reset the singleton service (for testing)."""
    global _default_service
    _default_service = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def reconcile_draft(
    draft: DraftReceipt,
    current_excel_values: Optional[Dict[str, Any]] = None,
    current_etag: Optional[str] = None,
) -> SyncReconciliationResult:
    """
    Convenience function to reconcile a draft.
    
    Args:
        draft: The DraftReceipt to reconcile
        current_excel_values: Current Excel row values
        current_etag: Current file ETag
        
    Returns:
        SyncReconciliationResult
    """
    return get_sync_reconciliation_service().reconcile_draft(
        draft=draft,
        current_excel_values=current_excel_values,
        current_etag=current_etag,
    )


def create_checkpoint_for_draft(
    draft: DraftReceipt,
    file_id: str,
    etag: Optional[str] = None,
    row_values: Optional[Dict[str, Any]] = None,
) -> CheckpointCreationResult:
    """
    Convenience function to create a checkpoint for a draft.
    
    Args:
        draft: The sent DraftReceipt
        file_id: OneDrive file ID
        etag: File ETag
        row_values: Row values
        
    Returns:
        CheckpointCreationResult
    """
    return get_sync_reconciliation_service().create_post_send_checkpoint(
        draft=draft,
        file_id=file_id,
        etag=etag,
        row_values=row_values,
    )
