"""
Phase 12B-2: External Change Detector Service

Detects external modifications to Excel data by comparing current state
against stored checkpoints. Designed for polling-based sync workflows.

Features:
    - Deterministic change detection outcomes
    - ETag-based and hash-based comparisons
    - Honest reporting when data is insufficient
    - Integration with SyncCheckpointService
    - No live Graph API calls (works with provided values)

Detection Outcomes:
    - NO_CHANGE: Current state matches checkpoint
    - ETAG_CHANGED: ETag differs (file-level change)
    - HASH_CHANGED: Content hash differs (row-level change)
    - BOTH_CHANGED: Both ETag and hash differ
    - INSUFFICIENT_DATA: Cannot determine (missing checkpoint or values)
    - CHECKPOINT_MISSING: No checkpoint exists for comparison

This implementation is:
    - Environment-independent (no live Graph calls)
    - Polling-friendly (designed for periodic checks)
    - Deterministic (consistent results given same inputs)
    - Honest (clearly reports when detection is impossible)

Author: Phase 12B-2
Date: 2026-03-28
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models.phase12_contracts import (
    SyncCheckpoint,
    ExternalChangeResult,
    ChangeSource,
    IExternalChangeDetector,
)
from app.services.sync_checkpoint_service import (
    SyncCheckpointService,
    get_sync_checkpoint_service,
    compute_checkpoint_hash,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DETECTION OUTCOME ENUM
# =============================================================================

class ChangeDetectionOutcome(str, Enum):
    """Outcome of external change detection.
    
    Represents the result of comparing current state against checkpoint.
    
    Attributes:
        NO_CHANGE: Current state matches checkpoint exactly
        ETAG_CHANGED: File-level ETag changed (file was modified)
        HASH_CHANGED: Content hash changed (row data differs)
        BOTH_CHANGED: Both ETag and hash differ
        CHECKPOINT_MISSING: No checkpoint exists for this file
        INSUFFICIENT_DATA: Cannot determine (missing current values)
        COMPARISON_ERROR: Error during comparison
    """
    NO_CHANGE = "NO_CHANGE"
    ETAG_CHANGED = "ETAG_CHANGED"
    HASH_CHANGED = "HASH_CHANGED"
    BOTH_CHANGED = "BOTH_CHANGED"
    CHECKPOINT_MISSING = "CHECKPOINT_MISSING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    COMPARISON_ERROR = "COMPARISON_ERROR"


# =============================================================================
# DETECTION RESULT
# =============================================================================

@dataclass
class ChangeDetectionResult:
    """Detailed result of external change detection.
    
    Provides comprehensive information about detected changes
    and the comparison process.
    
    Attributes:
        file_id: OneDrive file ID that was checked
        outcome: Detection outcome
        has_changes: True if any change was detected
        etag_changed: True if ETag differs from checkpoint
        hash_changed: True if hash differs from checkpoint
        checkpoint_etag: ETag from checkpoint (if exists)
        current_etag: Current ETag provided for comparison
        checkpoint_hash: Hash from checkpoint (if exists)
        current_hash: Current hash provided for comparison
        detected_at: Timestamp of this detection
        time_since_checkpoint: Seconds since checkpoint was created
        details: Additional diagnostic information
    """
    file_id: str
    outcome: ChangeDetectionOutcome
    has_changes: bool = False
    etag_changed: Optional[bool] = None
    hash_changed: Optional[bool] = None
    checkpoint_etag: Optional[str] = None
    current_etag: Optional[str] = None
    checkpoint_hash: Optional[str] = None
    current_hash: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    time_since_checkpoint: Optional[float] = None
    details: Optional[str] = None
    worksheet_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_id": self.file_id,
            "outcome": self.outcome.value,
            "has_changes": self.has_changes,
            "etag_changed": self.etag_changed,
            "hash_changed": self.hash_changed,
            "checkpoint_etag": self.checkpoint_etag,
            "current_etag": self.current_etag,
            "checkpoint_hash": self.checkpoint_hash,
            "current_hash": self.current_hash,
            "detected_at": self.detected_at.isoformat(),
            "time_since_checkpoint": self.time_since_checkpoint,
            "details": self.details,
            "worksheet_name": self.worksheet_name,
        }
    
    def to_external_change_result(self) -> ExternalChangeResult:
        """Convert to Phase 12B contract ExternalChangeResult.
        
        Returns:
            ExternalChangeResult for contract compatibility
        """
        # Determine change source based on outcome
        change_source = None
        if self.has_changes:
            change_source = ChangeSource.UNKNOWN  # Cannot determine without Graph context
        
        return ExternalChangeResult(
            file_id=self.file_id,
            has_changes=self.has_changes,
            change_source=change_source,
            changed_fields=[],  # Would require row-level comparison
            previous_etag=self.checkpoint_etag,
            current_etag=self.current_etag,
            detected_at=self.detected_at,
        )
    
    @property
    def is_conclusive(self) -> bool:
        """True if detection outcome is conclusive (not insufficient/error)."""
        return self.outcome not in (
            ChangeDetectionOutcome.INSUFFICIENT_DATA,
            ChangeDetectionOutcome.COMPARISON_ERROR,
            ChangeDetectionOutcome.CHECKPOINT_MISSING,
        )


# =============================================================================
# EXTERNAL CHANGE DETECTOR SERVICE
# =============================================================================

class ExternalChangeDetectorService(IExternalChangeDetector):
    """
    Service for detecting external changes to Excel data.
    
    Compares current state (provided) against stored checkpoints
    to determine if external modifications occurred.
    
    This service does NOT make live Graph API calls.
    All comparison values must be provided by the caller.
    
    Usage:
        detector = ExternalChangeDetectorService()
        
        # Detect changes with provided current state
        result = detector.detect_changes_with_values(
            file_id="abc123",
            current_etag="W/\"new...\"",
            current_hash="xyz789..."
        )
        
        if result.has_changes:
            print(f"External change detected: {result.outcome}")
    """
    
    def __init__(
        self,
        checkpoint_service: Optional[SyncCheckpointService] = None
    ):
        """
        Initialize the detector.
        
        Args:
            checkpoint_service: Optional SyncCheckpointService instance.
                               Uses singleton if not provided.
        """
        self._checkpoint_service = checkpoint_service or get_sync_checkpoint_service()
        self._detection_count = 0
        self._change_count = 0
        
        logger.info("ExternalChangeDetectorService initialized")
    
    # -------------------------------------------------------------------------
    # INTERFACE IMPLEMENTATION (IExternalChangeDetector)
    # -------------------------------------------------------------------------
    
    def detect_changes(
        self,
        file_id: str,
        since_etag: Optional[str] = None
    ) -> ExternalChangeResult:
        """Detect changes (interface method).
        
        NOTE: This interface method requires live Graph access which is
        deferred until full polling integration. Use detect_changes_with_values()
        for checkpoint-based detection.
        
        Args:
            file_id: OneDrive file ID to check
            since_etag: Optional ETag to compare against
            
        Returns:
            ExternalChangeResult indicating detection status
        """
        # If etag provided, do checkpoint-based comparison
        if since_etag:
            result = self.detect_changes_with_values(
                file_id=file_id,
                current_etag=since_etag
            )
            return result.to_external_change_result()
        
        # Without current values, we cannot detect - return insufficient data
        logger.debug(f"detect_changes called without current values for {file_id}")
        return ExternalChangeResult(
            file_id=file_id,
            has_changes=False,
            change_source=ChangeSource.UNKNOWN,
            detected_at=datetime.utcnow(),
        )
    
    # -------------------------------------------------------------------------
    # MAIN DETECTION API
    # -------------------------------------------------------------------------
    
    def detect_changes_with_values(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        current_etag: Optional[str] = None,
        current_hash: Optional[str] = None,
        current_row_values: Optional[Dict[str, Any]] = None
    ) -> ChangeDetectionResult:
        """Detect external changes by comparing current values to checkpoint.
        
        This is the main detection method. Provide current values from
        the caller (e.g., from a polling cycle or user request).
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            current_etag: Current file ETag (from Graph API)
            current_hash: Current row hash (pre-computed)
            current_row_values: Current row values (will compute hash if provided)
            
        Returns:
            ChangeDetectionResult with detection outcome
        """
        self._detection_count += 1
        
        try:
            # Get checkpoint
            checkpoint = self._checkpoint_service.get_checkpoint_for_file(
                file_id=file_id,
                worksheet_name=worksheet_name
            )
            
            if not checkpoint:
                logger.debug(f"No checkpoint found for {file_id}")
                return ChangeDetectionResult(
                    file_id=file_id,
                    outcome=ChangeDetectionOutcome.CHECKPOINT_MISSING,
                    has_changes=False,
                    details="No checkpoint exists for this file",
                    worksheet_name=worksheet_name,
                )
            
            # Compute hash from values if provided
            if current_row_values and not current_hash:
                current_hash = compute_checkpoint_hash(current_row_values)
            
            # Determine what comparisons are possible
            can_compare_etag = (
                checkpoint.last_etag is not None and 
                current_etag is not None
            )
            can_compare_hash = (
                checkpoint.last_row_hash is not None and 
                current_hash is not None
            )
            
            if not can_compare_etag and not can_compare_hash:
                logger.debug(f"Insufficient data for comparison on {file_id}")
                return ChangeDetectionResult(
                    file_id=file_id,
                    outcome=ChangeDetectionOutcome.INSUFFICIENT_DATA,
                    has_changes=False,
                    checkpoint_etag=checkpoint.last_etag,
                    current_etag=current_etag,
                    checkpoint_hash=checkpoint.last_row_hash,
                    current_hash=current_hash,
                    time_since_checkpoint=self._checkpoint_service.get_time_since_last_sync(
                        file_id, worksheet_name
                    ),
                    details="Neither ETag nor hash comparison possible",
                    worksheet_name=worksheet_name,
                )
            
            # Perform comparisons
            etag_changed = None
            hash_changed = None
            
            if can_compare_etag:
                etag_changed = checkpoint.last_etag != current_etag
            
            if can_compare_hash:
                hash_changed = checkpoint.last_row_hash != current_hash
            
            # Determine outcome
            outcome = self._determine_outcome(etag_changed, hash_changed)
            has_changes = outcome in (
                ChangeDetectionOutcome.ETAG_CHANGED,
                ChangeDetectionOutcome.HASH_CHANGED,
                ChangeDetectionOutcome.BOTH_CHANGED,
            )
            
            if has_changes:
                self._change_count += 1
                logger.info(
                    f"External change detected for {file_id}: {outcome.value}"
                )
            
            return ChangeDetectionResult(
                file_id=file_id,
                outcome=outcome,
                has_changes=has_changes,
                etag_changed=etag_changed,
                hash_changed=hash_changed,
                checkpoint_etag=checkpoint.last_etag,
                current_etag=current_etag,
                checkpoint_hash=checkpoint.last_row_hash,
                current_hash=current_hash,
                time_since_checkpoint=self._checkpoint_service.get_time_since_last_sync(
                    file_id, worksheet_name
                ),
                worksheet_name=worksheet_name,
            )
            
        except Exception as e:
            logger.error(f"Error during change detection for {file_id}: {e}")
            return ChangeDetectionResult(
                file_id=file_id,
                outcome=ChangeDetectionOutcome.COMPARISON_ERROR,
                has_changes=False,
                details=str(e),
                worksheet_name=worksheet_name,
            )
    
    def detect_changes_for_draft(
        self,
        draft_id: str,
        file_id: str,
        worksheet_name: Optional[str] = None,
        current_excel_hash: Optional[str] = None,
        current_etag: Optional[str] = None
    ) -> ChangeDetectionResult:
        """Convenience method for draft-level change detection.
        
        Args:
            draft_id: Draft ID (for logging/metadata)
            file_id: OneDrive file ID
            worksheet_name: Worksheet name
            current_excel_hash: Current Excel row hash
            current_etag: Current file ETag
            
        Returns:
            ChangeDetectionResult
        """
        result = self.detect_changes_with_values(
            file_id=file_id,
            worksheet_name=worksheet_name,
            current_etag=current_etag,
            current_hash=current_excel_hash
        )
        
        # Add draft context to details
        if result.details:
            result.details = f"[draft={draft_id}] {result.details}"
        else:
            result.details = f"[draft={draft_id}]"
        
        return result
    
    # -------------------------------------------------------------------------
    # BATCH DETECTION
    # -------------------------------------------------------------------------
    
    def detect_changes_batch(
        self,
        checks: List[Dict[str, Any]]
    ) -> List[ChangeDetectionResult]:
        """Perform batch change detection.
        
        Args:
            checks: List of check specifications, each containing:
                   - file_id (required)
                   - worksheet_name (optional)
                   - current_etag (optional)
                   - current_hash (optional)
                   
        Returns:
            List of ChangeDetectionResult, one per check
        """
        results = []
        
        for check in checks:
            result = self.detect_changes_with_values(
                file_id=check["file_id"],
                worksheet_name=check.get("worksheet_name"),
                current_etag=check.get("current_etag"),
                current_hash=check.get("current_hash"),
            )
            results.append(result)
        
        logger.info(
            f"Batch detection: {len(results)} checks, "
            f"{sum(1 for r in results if r.has_changes)} changes detected"
        )
        return results
    
    # -------------------------------------------------------------------------
    # CHECKPOINT INTEGRATION
    # -------------------------------------------------------------------------
    
    def update_checkpoint_after_detection(
        self,
        file_id: str,
        current_etag: Optional[str] = None,
        current_hash: Optional[str] = None,
        worksheet_name: Optional[str] = None
    ) -> bool:
        """Update checkpoint after processing detected changes.
        
        Call this after handling a detected external change to
        update the baseline for future comparisons.
        
        Args:
            file_id: OneDrive file ID
            current_etag: New ETag to record
            current_hash: New hash to record
            worksheet_name: Optional worksheet name
            
        Returns:
            True if checkpoint updated, False if not found
        """
        result = self._checkpoint_service.update_checkpoint(
            file_id=file_id,
            worksheet_name=worksheet_name,
            new_etag=current_etag,
            new_row_hash=current_hash
        )
        
        if result:
            logger.debug(f"Updated checkpoint after detection: {file_id}")
            return True
        return False
    
    def create_initial_checkpoint(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        current_etag: Optional[str] = None,
        current_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SyncCheckpoint:
        """Create an initial checkpoint for a file.
        
        Call this when first tracking a file (e.g., on first write).
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            current_etag: Current ETag
            current_hash: Current row hash
            metadata: Additional metadata
            
        Returns:
            Created SyncCheckpoint
        """
        return self._checkpoint_service.create_checkpoint(
            file_id=file_id,
            worksheet_name=worksheet_name,
            etag=current_etag,
            row_hash=current_hash,
            metadata=metadata
        )
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    
    def _determine_outcome(
        self,
        etag_changed: Optional[bool],
        hash_changed: Optional[bool]
    ) -> ChangeDetectionOutcome:
        """Determine detection outcome from comparison results."""
        
        # Both can be compared
        if etag_changed is not None and hash_changed is not None:
            if etag_changed and hash_changed:
                return ChangeDetectionOutcome.BOTH_CHANGED
            elif etag_changed:
                return ChangeDetectionOutcome.ETAG_CHANGED
            elif hash_changed:
                return ChangeDetectionOutcome.HASH_CHANGED
            else:
                return ChangeDetectionOutcome.NO_CHANGE
        
        # Only ETag comparison possible
        if etag_changed is not None:
            if etag_changed:
                return ChangeDetectionOutcome.ETAG_CHANGED
            else:
                return ChangeDetectionOutcome.NO_CHANGE
        
        # Only hash comparison possible
        if hash_changed is not None:
            if hash_changed:
                return ChangeDetectionOutcome.HASH_CHANGED
            else:
                return ChangeDetectionOutcome.NO_CHANGE
        
        # Should not reach here if called correctly
        return ChangeDetectionOutcome.INSUFFICIENT_DATA
    
    @property
    def detection_count(self) -> int:
        """Total number of detections performed."""
        return self._detection_count
    
    @property
    def change_count(self) -> int:
        """Total number of changes detected."""
        return self._change_count
    
    @property
    def checkpoint_service(self) -> SyncCheckpointService:
        """Get the associated checkpoint service."""
        return self._checkpoint_service


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_external_change_detector: Optional[ExternalChangeDetectorService] = None


def get_external_change_detector() -> ExternalChangeDetectorService:
    """Get the singleton ExternalChangeDetectorService instance.
    
    Returns:
        ExternalChangeDetectorService singleton instance
    """
    global _external_change_detector
    
    if _external_change_detector is None:
        _external_change_detector = ExternalChangeDetectorService()
    
    return _external_change_detector


def reset_external_change_detector() -> None:
    """Reset the singleton (for testing)."""
    global _external_change_detector
    _external_change_detector = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def detect_external_change(
    file_id: str,
    current_etag: Optional[str] = None,
    current_hash: Optional[str] = None,
    worksheet_name: Optional[str] = None
) -> ChangeDetectionResult:
    """Convenience function for quick change detection.
    
    Args:
        file_id: OneDrive file ID
        current_etag: Current file ETag
        current_hash: Current row hash
        worksheet_name: Optional worksheet name
        
    Returns:
        ChangeDetectionResult
    """
    detector = get_external_change_detector()
    return detector.detect_changes_with_values(
        file_id=file_id,
        worksheet_name=worksheet_name,
        current_etag=current_etag,
        current_hash=current_hash
    )


def has_external_change(
    file_id: str,
    current_etag: Optional[str] = None,
    current_hash: Optional[str] = None,
    worksheet_name: Optional[str] = None
) -> Optional[bool]:
    """Quick check if external change occurred.
    
    Args:
        file_id: OneDrive file ID
        current_etag: Current file ETag
        current_hash: Current row hash
        worksheet_name: Optional worksheet name
        
    Returns:
        True if change detected, False if no change, None if inconclusive
    """
    result = detect_external_change(
        file_id=file_id,
        current_etag=current_etag,
        current_hash=current_hash,
        worksheet_name=worksheet_name
    )
    
    if not result.is_conclusive:
        return None
    
    return result.has_changes
