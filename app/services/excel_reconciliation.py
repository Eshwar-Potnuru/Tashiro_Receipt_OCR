"""
Phase 11.B: Excel Reconciliation Service

Handles draft-to-Excel reconciliation when Excel is the authority (Option A').

The Excel Reconciliation Service provides:
1. Conflict detection between draft state and Excel authority
2. Hash-based comparison for efficient sync checks
3. Reconciliation workflow when conflicts are detected
4. Audit logging of all reconciliation events

Architecture:
    Draft (local) ← check conflict → Excel (OneDrive authority)
                  ↓
    If conflict detected → log to audit → trigger resolution

Usage:
    from app.services.excel_reconciliation import ExcelReconciliationService
    
    recon_service = ExcelReconciliationService()
    
    # Check if draft is in sync with Excel
    is_synced = recon_service.check_sync_status(draft)
    
    # Detect and log conflicts
    conflicts = recon_service.detect_conflicts(draft)
    
    # Sync draft with Excel values (Excel wins)
    recon_service.sync_draft_from_excel(draft)

Phase 11B-2 Additions:
    # Check draft consistency (no external calls required)
    result = recon_service.check_draft_consistency(draft)
    
    # Check with optional Excel values (for live scenarios)
    result = recon_service.check_draft_consistency(draft, excel_values=current_excel)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.draft import DraftReceipt, DraftStatus

logger = logging.getLogger(__name__)


# =============================================================================
# PHASE 11B-2: CONSISTENCY STATUS & CONFLICT SEVERITY ENUMS
# =============================================================================

class ConsistencyStatus(str, Enum):
    """Draft-to-Excel consistency status (Phase 11B-2).
    
    Represents the result of comparing draft state against known baselines.
    
    Attributes:
        CONSISTENT: No changes detected on either side
        LOCAL_CHANGE: Draft was modified locally (vs pre_edit_snapshot)
        EXTERNAL_CHANGE: Excel was modified externally (requires live PoC to detect)
        CONFLICT: Both draft and Excel were modified (bidirectional conflict)
        UNKNOWN: Cannot determine - missing baseline metadata
    
    Note:
        EXTERNAL_CHANGE detection requires live Excel access (Phase 10 PoC).
        Until live PoC passes, this status can only be set when Excel values
        are explicitly provided for comparison.
    """
    CONSISTENT = "CONSISTENT"
    LOCAL_CHANGE = "LOCAL_CHANGE"
    EXTERNAL_CHANGE = "EXTERNAL_CHANGE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class ConflictSeverity(str, Enum):
    """Severity level for detected conflicts (Phase 11B-2).
    
    Attributes:
        NONE: No conflict
        LOW: Minor discrepancy (e.g., whitespace, formatting)
        MEDIUM: Field value differs but not critical (e.g., memo changed)
        HIGH: Financial value differs (total_amount, tax amounts)
        CRITICAL: Multiple financial fields differ or key identifiers changed
    """
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Financial fields that trigger HIGH/CRITICAL severity
_FINANCIAL_FIELDS = {"total_amount", "tax_10_amount", "tax_8_amount"}
# Identity fields that trigger HIGH severity
_IDENTITY_FIELDS = {"vendor_name", "receipt_date", "invoice_number"}


@dataclass
class ConsistencyCheckResult:
    """Result of a draft consistency check (Phase 11B-2).
    
    Provides detailed information about the consistency state between
    a draft and its known baselines (pre_edit_snapshot, excel_last_known_values).
    
    Attributes:
        status: Overall consistency status
        severity: Conflict severity (if conflict detected)
        local_changed_fields: Fields changed locally (vs pre_edit_snapshot)
        external_changed_fields: Fields changed externally (vs excel_last_known_values)
        checked_at: Timestamp of this check
        has_baseline: True if pre_edit_snapshot exists
        has_excel_baseline: True if excel_last_known_values exists
        draft_hash: Current hash of draft receipt values
        baseline_hash: Hash of pre_edit_snapshot (if exists)
        excel_hash: Stored excel_row_hash (if exists)
        details: Additional diagnostic information
    
    Example:
        >>> result = ConsistencyCheckResult(
        ...     status=ConsistencyStatus.LOCAL_CHANGE,
        ...     severity=ConflictSeverity.MEDIUM,
        ...     local_changed_fields=["memo", "account_title"],
        ... )
    """
    status: ConsistencyStatus
    severity: ConflictSeverity = ConflictSeverity.NONE
    local_changed_fields: List[str] = field(default_factory=list)
    external_changed_fields: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)
    has_baseline: bool = False
    has_excel_baseline: bool = False
    draft_hash: Optional[str] = None
    baseline_hash: Optional[str] = None
    excel_hash: Optional[str] = None
    details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "severity": self.severity.value,
            "local_changed_fields": self.local_changed_fields,
            "external_changed_fields": self.external_changed_fields,
            "checked_at": self.checked_at.isoformat(),
            "has_baseline": self.has_baseline,
            "has_excel_baseline": self.has_excel_baseline,
            "draft_hash": self.draft_hash,
            "baseline_hash": self.baseline_hash,
            "excel_hash": self.excel_hash,
            "details": self.details,
        }
    
    @property
    def is_consistent(self) -> bool:
        """True if status is CONSISTENT."""
        return self.status == ConsistencyStatus.CONSISTENT
    
    @property
    def has_conflict(self) -> bool:
        """True if status is CONFLICT."""
        return self.status == ConsistencyStatus.CONFLICT
    
    @property
    def has_local_changes(self) -> bool:
        """True if local changes detected."""
        return len(self.local_changed_fields) > 0
    
    @property
    def has_external_changes(self) -> bool:
        """True if external changes detected."""
        return len(self.external_changed_fields) > 0


class ExcelConflict:
    """Represents a conflict between draft and Excel values."""
    
    def __init__(
        self,
        field_name: str,
        draft_value: Any,
        excel_value: Any,
        cell_address: Optional[str] = None,
    ):
        self.field_name = field_name
        self.draft_value = draft_value
        self.excel_value = excel_value
        self.cell_address = cell_address
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "draft_value": self.draft_value,
            "excel_value": self.excel_value,
            "cell_address": self.cell_address,
        }


class ExcelReconciliationService:
    """
    Service for reconciling draft state with Excel authority (Phase 11.B).
    
    Under Option A' architecture, Excel is the single source of truth for
    SENT receipts. This service handles:
    - Detecting when draft and Excel are out of sync
    - Computing hashes for efficient comparison
    - Logging conflicts to audit trail
    - Resolving conflicts (Excel wins by default)
    """
    
    # Fields that map between Receipt and Excel columns
    RECONCILE_FIELDS = [
        "receipt_date",
        "vendor_name",
        "total_amount",
        "tax_10_amount",
        "tax_8_amount",
        "account_title",
        "memo",
        "invoice_number",
        "business_location_id",
        "staff_id",
    ]
    
    def __init__(self, audit_service=None):
        """
        Initialize the reconciliation service.
        
        Args:
            audit_service: Optional PostSendAuditService for logging conflicts.
                          If None, will lazy-import when needed.
        """
        self._audit_service = audit_service
    
    @property
    def audit_service(self):
        """Lazy-load the audit service."""
        if self._audit_service is None:
            from app.services.post_send_audit import PostSendAuditService
            self._audit_service = PostSendAuditService()
        return self._audit_service
    
    def compute_row_hash(self, values: Dict[str, Any]) -> str:
        """
        Compute a SHA-256 hash of row values for sync comparison.
        
        Args:
            values: Dictionary of field values to hash
            
        Returns:
            Hex string of the hash
        """
        # Sort keys for deterministic hashing
        sorted_items = sorted(values.items())
        
        # Convert to JSON with consistent formatting
        json_str = json.dumps(sorted_items, sort_keys=True, default=str)
        
        # Compute SHA-256
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    def extract_reconcile_values(self, draft: DraftReceipt) -> Dict[str, Any]:
        """
        Extract the reconcilable field values from a draft.
        
        Args:
            draft: The DraftReceipt to extract values from
            
        Returns:
            Dictionary of field name -> value for reconcilable fields
        """
        values = {}
        receipt = draft.receipt
        
        for field in self.RECONCILE_FIELDS:
            val = getattr(receipt, field, None)
            # Normalize types for consistent hashing
            if hasattr(val, "__str__") and val is not None:
                values[field] = str(val)
            else:
                values[field] = val
        
        return values
    
    def check_sync_status(
        self,
        draft: DraftReceipt,
        excel_values: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if a draft is in sync with Excel.
        
        If excel_values is None, this method assumes Excel hasn't been read yet
        and relies on the stored hash (excel_row_hash).
        
        Args:
            draft: The draft to check
            excel_values: Current values from Excel (if available)
            
        Returns:
            True if in sync (no conflict), False if out of sync
        """
        if draft.status != DraftStatus.SENT:
            # Only SENT drafts need reconciliation with Excel
            return True
        
        if not draft.excel_row_hash:
            # No previous hash - assume first sync needed
            return False
        
        if excel_values is None:
            # No Excel values to compare - can't detect conflict
            # Return True to avoid false positives
            return True
        
        # Compute hash of current Excel values
        excel_hash = self.compute_row_hash(excel_values)
        
        # Compare with stored hash
        return draft.excel_row_hash == excel_hash
    
    def detect_conflicts(
        self,
        draft: DraftReceipt,
        excel_values: Dict[str, Any],
    ) -> List[ExcelConflict]:
        """
        Detect field-level conflicts between draft and Excel.
        
        Compares each reconcilable field and returns a list of conflicts
        where the values differ.
        
        Args:
            draft: The draft to compare
            excel_values: Current values from Excel
            
        Returns:
            List of ExcelConflict objects for fields that differ
        """
        conflicts = []
        draft_values = self.extract_reconcile_values(draft)
        
        for field in self.RECONCILE_FIELDS:
            draft_val = draft_values.get(field)
            excel_val = excel_values.get(field)
            
            # Normalize for comparison
            draft_str = str(draft_val) if draft_val is not None else None
            excel_str = str(excel_val) if excel_val is not None else None
            
            if draft_str != excel_str:
                conflicts.append(ExcelConflict(
                    field_name=field,
                    draft_value=draft_val,
                    excel_value=excel_val,
                ))
        
        return conflicts
    
    def log_conflict(
        self,
        draft: DraftReceipt,
        conflict: ExcelConflict,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Log a conflict to the audit trail.
        
        Args:
            draft: The draft with the conflict
            conflict: The conflict details
            user_id: User who encountered the conflict
            
        Returns:
            The edit_id of the audit entry
        """
        return self.audit_service.log_excel_conflict(
            draft_id=draft.draft_id,
            field_name=conflict.field_name,
            draft_value=conflict.draft_value,
            excel_value=conflict.excel_value,
            user_id=user_id,
            file_id=draft.format1_file_id or draft.format2_file_id,
            row_index=draft.format1_row_index or draft.format2_row_index,
        )
    
    def update_sync_state(
        self,
        draft: DraftReceipt,
        excel_values: Dict[str, Any],
    ) -> DraftReceipt:
        """
        Update the draft's sync state after reading from Excel.
        
        Sets the excel_row_hash and excel_row_synced_at fields.
        Clears any conflict flag if values match.
        
        Args:
            draft: The draft to update
            excel_values: Current values from Excel
            
        Returns:
            The updated draft (not persisted - caller must save)
        """
        # Compute and store hash
        draft.excel_row_hash = self.compute_row_hash(excel_values)
        draft.excel_row_synced_at = datetime.utcnow()
        draft.excel_last_known_values = json.dumps(excel_values, default=str)
        
        # Check for conflicts
        conflicts = self.detect_conflicts(draft, excel_values)
        draft.excel_conflict_detected = len(conflicts) > 0
        
        return draft
    
    def resolve_conflict_excel_wins(
        self,
        draft: DraftReceipt,
        excel_values: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Tuple[DraftReceipt, List[str]]:
        """
        Resolve conflicts by accepting Excel values (Excel is authority).
        
        Updates the draft's receipt with values from Excel and logs
        the resolution to the audit trail.
        
        Args:
            draft: The draft with conflicts
            excel_values: Current values from Excel (these win)
            user_id: User performing the resolution
            
        Returns:
            Tuple of (updated_draft, list of edit_ids for logged changes)
        """
        from app.models.schema import Receipt
        
        edit_ids = []
        receipt = draft.receipt
        
        # Log each field change
        for field in self.RECONCILE_FIELDS:
            old_val = getattr(receipt, field, None)
            new_val = excel_values.get(field)
            
            old_str = str(old_val) if old_val is not None else None
            new_str = str(new_val) if new_val is not None else None
            
            if old_str != new_str:
                # Log the change
                edit_id = self.audit_service.log_post_send_edit(
                    draft_id=draft.draft_id,
                    field_name=field,
                    old_value=old_val,
                    new_value=new_val,
                    user_id=user_id,
                    file_id=draft.format1_file_id,
                    row_index=draft.format1_row_index,
                    operation_type="EXCEL_CONFLICT_RESOLVED",
                )
                edit_ids.append(edit_id)
                
                # Update receipt field
                if hasattr(receipt, field):
                    setattr(receipt, field, new_val)
        
        # Update sync state
        draft.excel_row_hash = self.compute_row_hash(excel_values)
        draft.excel_row_synced_at = datetime.utcnow()
        draft.excel_last_known_values = json.dumps(excel_values, default=str)
        draft.excel_conflict_detected = False
        draft.updated_at = datetime.utcnow()
        
        logger.info(
            f"ExcelReconciliationService: Resolved conflicts for draft {draft.draft_id} "
            f"(Excel wins). Updated {len(edit_ids)} fields."
        )
        
        return draft, edit_ids
    
    def prepare_pre_edit_snapshot(self, draft: DraftReceipt) -> str:
        """
        Create a JSON snapshot of current receipt values before edit.
        
        Used for before/after comparison in post-send edits.
        
        Args:
            draft: The draft about to be edited
            
        Returns:
            JSON string of the current receipt values
        """
        values = self.extract_reconcile_values(draft)
        return json.dumps(values, default=str)

    # =========================================================================
    # PHASE 11B-2: CONSISTENCY CHECK LOGIC
    # =========================================================================

    def check_draft_consistency(
        self,
        draft: DraftReceipt,
        excel_values: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyCheckResult:
        """
        Check the consistency of a draft against its known baselines (Phase 11B-2).
        
        This method compares:
        1. Current draft values vs pre_edit_snapshot (local changes)
        2. Current draft values vs excel_last_known_values (baseline check)
        3. If excel_values provided, compares excel_last_known_values vs current Excel
        
        Args:
            draft: The draft to check
            excel_values: Optional current Excel values for external change detection.
                         If None, external change detection is skipped (requires live PoC).
        
        Returns:
            ConsistencyCheckResult with status, severity, and change details
        
        Note:
            For full EXTERNAL_CHANGE detection, excel_values must be provided.
            This requires live Excel access which depends on Phase 10 PoC passing.
            When excel_values is None, external changes cannot be detected and
            the check only compares against stored baselines.
        """
        # Get current draft values
        current_values = self.extract_reconcile_values(draft)
        draft_hash = self.compute_row_hash(current_values)
        
        # Check if baselines exist
        has_baseline = draft.pre_edit_snapshot is not None
        has_excel_baseline = draft.excel_last_known_values is not None
        
        # Parse stored baselines
        baseline_values = None
        excel_baseline_values = None
        baseline_hash = None
        
        if has_baseline:
            try:
                baseline_values = json.loads(draft.pre_edit_snapshot)
                baseline_hash = self.compute_row_hash(baseline_values)
            except (json.JSONDecodeError, TypeError):
                has_baseline = False
        
        if has_excel_baseline:
            try:
                excel_baseline_values = json.loads(draft.excel_last_known_values)
            except (json.JSONDecodeError, TypeError):
                has_excel_baseline = False
        
        # Detect local changes (draft vs pre_edit_snapshot)
        local_changed_fields = []
        if has_baseline and baseline_values:
            local_changed_fields = self._compare_values(baseline_values, current_values)
        
        # Detect external changes (excel_last_known_values vs current Excel)
        # This requires excel_values to be provided (live PoC dependency)
        external_changed_fields = []
        if excel_values is not None and has_excel_baseline and excel_baseline_values:
            external_changed_fields = self._compare_values(excel_baseline_values, excel_values)
        
        # Determine consistency status
        status = self._determine_consistency_status(
            has_baseline=has_baseline,
            has_excel_baseline=has_excel_baseline,
            local_changes=local_changed_fields,
            external_changes=external_changed_fields,
            excel_values_provided=(excel_values is not None),
        )
        
        # Determine conflict severity
        severity = self._determine_conflict_severity(
            status=status,
            local_changes=local_changed_fields,
            external_changes=external_changed_fields,
        )
        
        # Build details message
        details = self._build_consistency_details(
            status, has_baseline, has_excel_baseline, 
            excel_values is not None, local_changed_fields, external_changed_fields
        )
        
        return ConsistencyCheckResult(
            status=status,
            severity=severity,
            local_changed_fields=local_changed_fields,
            external_changed_fields=external_changed_fields,
            has_baseline=has_baseline,
            has_excel_baseline=has_excel_baseline,
            draft_hash=draft_hash,
            baseline_hash=baseline_hash,
            excel_hash=draft.excel_row_hash,
            details=details,
        )

    def _compare_values(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[str]:
        """
        Compare two value dictionaries and return list of changed fields.
        
        Args:
            baseline: Original values
            current: Current values
            
        Returns:
            List of field names that differ
        """
        changed = []
        all_fields = set(baseline.keys()) | set(current.keys())
        
        for field_name in all_fields:
            baseline_val = baseline.get(field_name)
            current_val = current.get(field_name)
            
            # Normalize for comparison
            baseline_str = str(baseline_val) if baseline_val is not None else None
            current_str = str(current_val) if current_val is not None else None
            
            if baseline_str != current_str:
                changed.append(field_name)
        
        return changed

    def _determine_consistency_status(
        self,
        has_baseline: bool,
        has_excel_baseline: bool,
        local_changes: List[str],
        external_changes: List[str],
        excel_values_provided: bool,
    ) -> ConsistencyStatus:
        """
        Determine the overall consistency status based on detected changes.
        
        Decision matrix:
        - No baselines → UNKNOWN
        - Both sides changed → CONFLICT
        - Only local changed → LOCAL_CHANGE
        - Only external changed → EXTERNAL_CHANGE
        - Neither changed → CONSISTENT
        
        Note:
            If excel_values_provided is False, we cannot detect external changes.
            In this case, we compare draft_hash vs stored excel_row_hash if available.
        """
        # If no baselines at all, we can't determine anything
        if not has_baseline and not has_excel_baseline:
            return ConsistencyStatus.UNKNOWN
        
        has_local = len(local_changes) > 0
        has_external = len(external_changes) > 0
        
        # If both sides changed, it's a conflict
        if has_local and has_external:
            return ConsistencyStatus.CONFLICT
        
        # If only local changed
        if has_local and not has_external:
            return ConsistencyStatus.LOCAL_CHANGE
        
        # If only external changed
        if has_external and not has_local:
            return ConsistencyStatus.EXTERNAL_CHANGE
        
        # Neither changed - but check if we even have data to compare
        if not has_baseline:
            # No pre_edit_snapshot means we can't know if local changes happened
            return ConsistencyStatus.UNKNOWN
        
        # Both exist, no changes detected
        return ConsistencyStatus.CONSISTENT

    def _determine_conflict_severity(
        self,
        status: ConsistencyStatus,
        local_changes: List[str],
        external_changes: List[str],
    ) -> ConflictSeverity:
        """
        Determine conflict severity based on which fields changed.
        
        Severity Rules:
        - CONSISTENT/UNKNOWN → NONE
        - LOCAL_CHANGE/EXTERNAL_CHANGE → based on fields changed
        - CONFLICT → highest severity of any changed field
        
        Field Categories:
        - Financial (total_amount, tax_*): HIGH (single) / CRITICAL (multiple)
        - Identity (vendor_name, receipt_date): HIGH
        - Other: LOW/MEDIUM
        """
        if status in (ConsistencyStatus.CONSISTENT, ConsistencyStatus.UNKNOWN):
            return ConflictSeverity.NONE
        
        # Combine all changed fields
        all_changes = set(local_changes) | set(external_changes)
        
        if not all_changes:
            return ConflictSeverity.NONE
        
        # Check for financial field changes
        financial_changes = all_changes & _FINANCIAL_FIELDS
        identity_changes = all_changes & _IDENTITY_FIELDS
        
        # CRITICAL: Multiple financial fields or financial + identity
        if len(financial_changes) > 1:
            return ConflictSeverity.CRITICAL
        if financial_changes and identity_changes:
            return ConflictSeverity.CRITICAL
        
        # HIGH: Any financial or identity field
        if financial_changes or identity_changes:
            return ConflictSeverity.HIGH
        
        # MEDIUM: Multiple non-critical fields
        if len(all_changes) > 1:
            return ConflictSeverity.MEDIUM
        
        # LOW: Single non-critical field
        return ConflictSeverity.LOW

    def _build_consistency_details(
        self,
        status: ConsistencyStatus,
        has_baseline: bool,
        has_excel_baseline: bool,
        excel_values_provided: bool,
        local_changes: List[str],
        external_changes: List[str],
    ) -> str:
        """Build a human-readable details message for the consistency check."""
        parts = []
        
        if status == ConsistencyStatus.UNKNOWN:
            if not has_baseline and not has_excel_baseline:
                parts.append("No baseline snapshots available.")
            elif not has_baseline:
                parts.append("Missing pre_edit_snapshot.")
            if not excel_values_provided:
                parts.append("External change detection skipped (no Excel values provided - requires live PoC).")
        
        elif status == ConsistencyStatus.CONSISTENT:
            parts.append("Draft is consistent with all baselines.")
        
        elif status == ConsistencyStatus.LOCAL_CHANGE:
            parts.append(f"Local changes detected: {', '.join(local_changes)}.")
        
        elif status == ConsistencyStatus.EXTERNAL_CHANGE:
            parts.append(f"External changes detected: {', '.join(external_changes)}.")
        
        elif status == ConsistencyStatus.CONFLICT:
            parts.append(f"CONFLICT: Local changed ({', '.join(local_changes)}), "
                        f"External changed ({', '.join(external_changes)}).")
        
        return " ".join(parts) if parts else ""

    def update_draft_reconciliation_state(
        self,
        draft: DraftReceipt,
        consistency_result: ConsistencyCheckResult,
    ) -> DraftReceipt:
        """
        Update draft fields based on a consistency check result (Phase 11B-2).
        
        This method updates the draft's reconciliation-related fields based on
        the consistency check result. It does NOT persist the draft - the caller
        must save the draft via DraftRepository.
        
        Args:
            draft: The draft to update
            consistency_result: Result from check_draft_consistency()
        
        Returns:
            The updated draft (not persisted - caller must save)
        
        Updates:
            - excel_conflict_detected: Set to True if status is CONFLICT
            - excel_row_synced_at: Updated if consistency check was performed
        """
        # Update conflict flag based on status
        draft.excel_conflict_detected = consistency_result.has_conflict
        
        # Update sync timestamp
        draft.excel_row_synced_at = consistency_result.checked_at
        
        # Update timestamp
        draft.updated_at = datetime.utcnow()
        
        logger.debug(
            f"ExcelReconciliationService: Updated reconciliation state for {draft.draft_id}. "
            f"Status={consistency_result.status.value}, Severity={consistency_result.severity.value}"
        )
        
        return draft

    def mark_conflict_detected(
        self,
        draft: DraftReceipt,
        reason: Optional[str] = None,
    ) -> DraftReceipt:
        """
        Explicitly mark a draft as having a conflict detected (Phase 11B-2).
        
        This is a convenience method for marking conflicts when they are
        detected through means other than check_draft_consistency().
        
        Args:
            draft: The draft to mark
            reason: Optional reason for the conflict
        
        Returns:
            The updated draft (not persisted - caller must save)
        """
        draft.excel_conflict_detected = True
        draft.updated_at = datetime.utcnow()
        
        logger.info(
            f"ExcelReconciliationService: Conflict marked for {draft.draft_id}. "
            f"Reason: {reason or 'unspecified'}"
        )
        
        return draft

    def clear_conflict(
        self,
        draft: DraftReceipt,
        resolved_by: Optional[str] = None,
    ) -> DraftReceipt:
        """
        Clear the conflict flag on a draft (Phase 11B-2).
        
        Call this after a conflict has been resolved.
        
        Args:
            draft: The draft to update
            resolved_by: Optional user_id who resolved the conflict
        
        Returns:
            The updated draft (not persisted - caller must save)
        """
        draft.excel_conflict_detected = False
        draft.updated_at = datetime.utcnow()
        
        logger.info(
            f"ExcelReconciliationService: Conflict cleared for {draft.draft_id}. "
            f"Resolved by: {resolved_by or 'system'}"
        )
        
        return draft


# Module-level singleton
_default_service: Optional[ExcelReconciliationService] = None


def get_excel_reconciliation_service() -> ExcelReconciliationService:
    """Get the default ExcelReconciliationService instance."""
    global _default_service
    if _default_service is None:
        _default_service = ExcelReconciliationService()
    return _default_service
