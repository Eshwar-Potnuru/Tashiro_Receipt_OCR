"""
Data Recovery Service (Phase 10 Foundation + Phase 12A-3 Integration)

Point-in-time restore capability using audit log history.

Features:
    - Reconstruct receipt state at any point in time
    - Roll back to previous versions
    - Recover deleted items (soft delete)
    - Export audit trail for compliance
    - Phase 12A: Recovery operation contracts integration

Author: Phase 10 Foundation, Phase 12A-3 Integration
Date: 2025-01-24
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

# Phase 12A Recovery Contracts
from app.models.phase12_contracts import (
    RecoveryOperationType,
    RecoveryOperationRequest,
    RecoveryOutcome,
    RecoveryOperationResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PHASE 12A-3: DEFERRED OPERATION TRACKING  
# =============================================================================

# Operations that require live Graph API (deferred until Graph credentials available)
DEFERRED_RECOVERY_OPERATIONS = frozenset({
    RecoveryOperationType.RETRY_SEND,       # Requires Graph API to re-send
    RecoveryOperationType.RESYNC_FROM_EXCEL,  # Requires Graph API to read Excel
})

# Operations that can be handled locally
LOCAL_RECOVERY_OPERATIONS = frozenset({
    RecoveryOperationType.REVERT_DRAFT,     # Uses local audit history
    RecoveryOperationType.MANUAL_OVERRIDE,   # Admin bypass, local only
})


@dataclass
class RecoveryPoint:
    """Represents a point in time where recovery is possible."""
    timestamp: datetime
    audit_id: str
    event_type: str
    description: str
    data_snapshot: Optional[Dict[str, Any]] = None


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    success: bool
    recovered_data: Optional[Dict[str, Any]] = None
    recovery_timestamp: Optional[datetime] = None
    error_message: Optional[str] = None
    audit_trail: List[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "recovered_data": self.recovered_data,
            "recovery_timestamp": self.recovery_timestamp.isoformat() if self.recovery_timestamp else None,
            "error_message": self.error_message,
            "audit_trail_count": len(self.audit_trail) if self.audit_trail else 0
        }


class DataRecoveryService:
    """
    Service for recovering receipt data from audit history.
    
    Uses the audit log to reconstruct previous states and enable
    point-in-time recovery of receipt data.
    
    Usage:
        recovery = DataRecoveryService(db_path)
        
        # List available recovery points
        points = recovery.get_recovery_points(receipt_id)
        
        # Recover to a specific point
        result = recovery.recover_to_point(receipt_id, points[0].timestamp)
        
        # Preview recovery without applying
        preview = recovery.preview_recovery(receipt_id, target_time)
    """
    
    def __init__(self, db_path: str = "app/Data/drafts.db"):
        """
        Initialize the recovery service.
        
        Args:
            db_path: Path to the SQLite database (defaults to drafts.db)
        """
        self._db_path = db_path
        logger.info(f"DataRecoveryService initialized (db={db_path})")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_recovery_points(
        self,
        receipt_id: str,
        limit: int = 50
    ) -> List[RecoveryPoint]:
        """
        Get available recovery points for a receipt.
        
        Args:
            receipt_id: ID of the receipt to get recovery points for
            limit: Maximum number of points to return
            
        Returns:
            List of RecoveryPoint objects, most recent first
        """
        conn = self._get_connection()
        try:
            # Check multiple audit tables that might exist
            points = []
            
            # Try post_send_edits table (Phase 9.R.3)
            try:
                cursor = conn.execute("""
                    SELECT 
                        edit_id,
                        receipt_id,
                        edited_at,
                        field_name,
                        old_value,
                        new_value,
                        edited_by
                    FROM post_send_edits
                    WHERE receipt_id = ?
                    ORDER BY edited_at DESC
                    LIMIT ?
                """, (receipt_id, limit))
                
                for row in cursor.fetchall():
                    try:
                        old_val = json.loads(row["old_value"]) if row["old_value"] else None
                    except (json.JSONDecodeError, TypeError):
                        old_val = row["old_value"]
                    
                    points.append(RecoveryPoint(
                        timestamp=datetime.fromisoformat(row["edited_at"]) if row["edited_at"] else datetime.utcnow(),
                        audit_id=row["edit_id"],
                        event_type="post_send_edit",
                        description=f"Field '{row['field_name']}' modified",
                        data_snapshot={"field": row["field_name"], "old_value": old_val}
                    ))
            except sqlite3.OperationalError:
                # Table doesn't exist
                pass
            
            # Try general audit_log table if it exists
            try:
                cursor = conn.execute("""
                    SELECT 
                        id,
                        timestamp,
                        event_type,
                        entity_id,
                        data
                    FROM audit_log
                    WHERE entity_id = ? OR entity_type = 'receipt'
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (receipt_id, limit))
                
                for row in cursor.fetchall():
                    try:
                        data = json.loads(row["data"]) if row["data"] else None
                    except (json.JSONDecodeError, TypeError):
                        data = None
                    
                    points.append(RecoveryPoint(
                        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.utcnow(),
                        audit_id=str(row["id"]),
                        event_type=row["event_type"] or "unknown",
                        description=f"Audit event: {row['event_type']}",
                        data_snapshot=data
                    ))
            except sqlite3.OperationalError:
                # Table doesn't exist
                pass
            
            # Sort all points by timestamp
            points.sort(key=lambda p: p.timestamp, reverse=True)
            return points[:limit]
            
        finally:
            conn.close()
    
    def get_receipt_history(
        self,
        receipt_id: str,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get the complete modification history for a receipt.
        
        Args:
            receipt_id: ID of the receipt
            from_time: Start of time range (optional)
            to_time: End of time range (optional)
            
        Returns:
            List of history entries
        """
        conn = self._get_connection()
        try:
            history = []
            
            # Get post-send edits
            try:
                params = [receipt_id]
                query = """
                    SELECT 
                        edit_id,
                        receipt_id,
                        edited_at,
                        field_name,
                        old_value,
                        new_value,
                        edited_by
                    FROM post_send_edits
                    WHERE receipt_id = ?
                """
                
                if from_time:
                    query += " AND edited_at >= ?"
                    params.append(from_time.isoformat())
                if to_time:
                    query += " AND edited_at <= ?"
                    params.append(to_time.isoformat())
                
                query += " ORDER BY edited_at DESC"
                
                cursor = conn.execute(query, params)
                
                for row in cursor.fetchall():
                    history.append({
                        "id": row["edit_id"],
                        "timestamp": row["edited_at"],
                        "event_type": "post_send_edit",
                        "field_name": row["field_name"],
                        "old_value": row["old_value"],
                        "new_value": row["new_value"],
                        "user": row["edited_by"],
                        "source": "post_send_edits"
                    })
            except sqlite3.OperationalError:
                pass
            
            return sorted(history, key=lambda h: h.get("timestamp", ""), reverse=True)
            
        finally:
            conn.close()
    
    def reconstruct_state(
        self,
        receipt_id: str,
        target_time: datetime
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Reconstruct the state of a receipt at a specific point in time.
        
        This works by getting the current state and "undoing" all changes
        that happened after the target time.
        
        Args:
            receipt_id: ID of the receipt
            target_time: Point in time to reconstruct
            
        Returns:
            Tuple of (reconstructed_state, applied_reversals)
        """
        conn = self._get_connection()
        try:
            # Get current state
            cursor = conn.execute("""
                SELECT * FROM drafts WHERE id = ?
            """, (receipt_id,))
            
            row = cursor.fetchone()
            if not row:
                return None, []
            
            # Convert to dict
            current_state = dict(row)
            
            # Parse receipt_data JSON
            if current_state.get("receipt_data"):
                try:
                    current_state["receipt_data"] = json.loads(current_state["receipt_data"])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # Get all edits after target_time (to undo them)
            reversals = []
            try:
                cursor = conn.execute("""
                    SELECT 
                        field_name,
                        old_value,
                        new_value,
                        edited_at
                    FROM post_send_edits
                    WHERE receipt_id = ? AND edited_at > ?
                    ORDER BY edited_at DESC
                """, (receipt_id, target_time.isoformat()))
                
                for row in cursor.fetchall():
                    reversals.append({
                        "field": row["field_name"],
                        "restore_to": row["old_value"],
                        "current": row["new_value"],
                        "edited_at": row["edited_at"]
                    })
                    
                    # Apply reversal to reconstructed state
                    field_name = row["field_name"]
                    old_value = row["old_value"]
                    
                    if field_name in current_state:
                        current_state[field_name] = old_value
                    elif isinstance(current_state.get("receipt_data"), dict):
                        # Try nested in receipt_data
                        if field_name in current_state["receipt_data"]:
                            try:
                                current_state["receipt_data"][field_name] = json.loads(old_value)
                            except (json.JSONDecodeError, TypeError):
                                current_state["receipt_data"][field_name] = old_value
                
            except sqlite3.OperationalError:
                pass
            
            return current_state, reversals
            
        finally:
            conn.close()
    
    def preview_recovery(
        self,
        receipt_id: str,
        target_time: datetime
    ) -> RecoveryResult:
        """
        Preview what a recovery operation would do without applying it.
        
        Args:
            receipt_id: ID of the receipt to recover
            target_time: Point in time to recover to
            
        Returns:
            RecoveryResult with preview data
        """
        try:
            reconstructed, reversals = self.reconstruct_state(receipt_id, target_time)
            
            if reconstructed is None:
                return RecoveryResult(
                    success=False,
                    error_message=f"Receipt {receipt_id} not found"
                )
            
            return RecoveryResult(
                success=True,
                recovered_data=reconstructed,
                recovery_timestamp=target_time,
                audit_trail=reversals
            )
            
        except Exception as e:
            logger.error(f"Preview recovery failed: {e}")
            return RecoveryResult(
                success=False,
                error_message=str(e)
            )
    
    def recover_to_point(
        self,
        receipt_id: str,
        target_time: datetime,
        dry_run: bool = False
    ) -> RecoveryResult:
        """
        Recover a receipt to a specific point in time.
        
        Args:
            receipt_id: ID of the receipt to recover
            target_time: Point in time to recover to
            dry_run: If True, only preview without applying
            
        Returns:
            RecoveryResult with outcome
        """
        if dry_run:
            return self.preview_recovery(receipt_id, target_time)
        
        conn = self._get_connection()
        try:
            # Reconstruct the state
            reconstructed, reversals = self.reconstruct_state(receipt_id, target_time)
            
            if reconstructed is None:
                return RecoveryResult(
                    success=False,
                    error_message=f"Receipt {receipt_id} not found"
                )
            
            if not reversals:
                return RecoveryResult(
                    success=True,
                    recovered_data=reconstructed,
                    recovery_timestamp=target_time,
                    audit_trail=[],
                    error_message="No changes to revert (already at target state)"
                )
            
            # Apply the recovery
            receipt_data = reconstructed.get("receipt_data")
            if isinstance(receipt_data, dict):
                receipt_data = json.dumps(receipt_data)
            
            conn.execute("""
                UPDATE drafts 
                SET receipt_data = ?,
                    updated_at = ?
                WHERE id = ?
            """, (receipt_data, datetime.utcnow().isoformat(), receipt_id))
            
            # Log the recovery action
            try:
                conn.execute("""
                    INSERT INTO post_send_edits (
                        edit_id, receipt_id, edited_at, field_name,
                        old_value, new_value, edited_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"recovery_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    receipt_id,
                    datetime.utcnow().isoformat(),
                    "_recovery_action",
                    json.dumps({"target_time": target_time.isoformat()}),
                    json.dumps({"reversals_applied": len(reversals)}),
                    "system_recovery"
                ))
            except sqlite3.OperationalError:
                # Table might not exist
                pass
            
            conn.commit()
            
            logger.info(f"Recovered receipt {receipt_id} to {target_time}, {len(reversals)} changes reverted")
            
            return RecoveryResult(
                success=True,
                recovered_data=reconstructed,
                recovery_timestamp=target_time,
                audit_trail=reversals
            )
            
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            conn.rollback()
            return RecoveryResult(
                success=False,
                error_message=str(e)
            )
        finally:
            conn.close()
    
    def export_audit_trail(
        self,
        receipt_id: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        Export audit trail for compliance/archival.
        
        Args:
            receipt_id: Optional filter by receipt ID
            from_time: Optional start time filter
            to_time: Optional end time filter
            format: Output format ("json" or "csv")
            
        Returns:
            Audit trail export data
        """
        conn = self._get_connection()
        try:
            entries = []
            
            # Build query
            query = """
                SELECT 
                    edit_id,
                    receipt_id,
                    edited_at,
                    field_name,
                    old_value,
                    new_value,
                    edited_by
                FROM post_send_edits
                WHERE 1=1
            """
            params = []
            
            if receipt_id:
                query += " AND receipt_id = ?"
                params.append(receipt_id)
            if from_time:
                query += " AND edited_at >= ?"
                params.append(from_time.isoformat())
            if to_time:
                query += " AND edited_at <= ?"
                params.append(to_time.isoformat())
            
            query += " ORDER BY edited_at DESC"
            
            try:
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    entries.append({
                        "edit_id": row["edit_id"],
                        "receipt_id": row["receipt_id"],
                        "timestamp": row["edited_at"],
                        "field": row["field_name"],
                        "old_value": row["old_value"],
                        "new_value": row["new_value"],
                        "user": row["edited_by"]
                    })
            except sqlite3.OperationalError:
                pass
            
            export_data = {
                "exported_at": datetime.utcnow().isoformat(),
                "filters": {
                    "receipt_id": receipt_id,
                    "from_time": from_time.isoformat() if from_time else None,
                    "to_time": to_time.isoformat() if to_time else None
                },
                "entry_count": len(entries),
                "entries": entries
            }
            
            if format == "csv":
                # Convert to CSV format
                if entries:
                    headers = list(entries[0].keys())
                    csv_lines = [",".join(headers)]
                    for entry in entries:
                        csv_lines.append(",".join(str(entry.get(h, "")) for h in headers))
                    export_data["csv"] = "\n".join(csv_lines)
            
            return export_data
            
        finally:
            conn.close()
    
    def get_deleted_receipts(
        self,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get list of deleted receipts that might be recoverable.
        
        Note: This requires soft-delete implementation. Currently returns
        empty list if hard deletes are used.
        
        Args:
            since: Only return receipts deleted after this time
            
        Returns:
            List of deleted receipt info
        """
        conn = self._get_connection()
        try:
            deleted = []
            
            # Check for deleted_at column (soft delete)
            try:
                query = """
                    SELECT id, receipt_data, deleted_at
                    FROM drafts
                    WHERE deleted_at IS NOT NULL
                """
                params = []
                
                if since:
                    query += " AND deleted_at >= ?"
                    params.append(since.isoformat())
                
                query += " ORDER BY deleted_at DESC"
                
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    deleted.append({
                        "id": row["id"],
                        "deleted_at": row["deleted_at"],
                        "recoverable": True
                    })
            except sqlite3.OperationalError:
                # No soft delete column exists
                logger.debug("Soft delete not implemented - cannot list deleted receipts")
            
            return deleted
            
        finally:
            conn.close()
    
    def create_snapshot(
        self,
        receipt_id: str,
        description: str = ""
    ) -> Optional[str]:
        """
        Create a manual snapshot/checkpoint for a receipt.
        
        Args:
            receipt_id: ID of the receipt
            description: Optional description of the snapshot
            
        Returns:
            Snapshot ID if successful, None otherwise
        """
        conn = self._get_connection()
        try:
            # Get current receipt state
            cursor = conn.execute("""
                SELECT * FROM drafts WHERE id = ?
            """, (receipt_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.error(f"Cannot snapshot: receipt {receipt_id} not found")
                return None
            
            # Create snapshot entry in audit log
            snapshot_id = f"snapshot_{receipt_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            try:
                conn.execute("""
                    INSERT INTO post_send_edits (
                        edit_id, receipt_id, edited_at, field_name,
                        old_value, new_value, edited_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    snapshot_id,
                    receipt_id,
                    datetime.utcnow().isoformat(),
                    "_manual_snapshot",
                    json.dumps(dict(row)),
                    json.dumps({"description": description}),
                    "user_snapshot"
                ))
                conn.commit()
                logger.info(f"Created snapshot {snapshot_id} for receipt {receipt_id}")
                return snapshot_id
                
            except sqlite3.OperationalError as e:
                logger.error(f"Failed to create snapshot: {e}")
                return None
            
        finally:
            conn.close()

    # =========================================================================
    # PHASE 12A-3: RECOVERY OPERATION CONTRACT INTEGRATION
    # =========================================================================
    
    def is_operation_deferred(self, operation_type: RecoveryOperationType) -> bool:
        """
        Check if a recovery operation type requires deferred handling.
        
        Deferred operations require live Graph API which may not be available.
        
        Args:
            operation_type: The type of recovery operation
            
        Returns:
            True if the operation requires Graph API (deferred), False if local-only
        """
        return operation_type in DEFERRED_RECOVERY_OPERATIONS
    
    def is_operation_supported(self, operation_type: RecoveryOperationType) -> bool:
        """
        Check if a recovery operation type is currently supported.
        
        Args:
            operation_type: The type of recovery operation
            
        Returns:
            True if the operation can be executed locally
        """
        return operation_type in LOCAL_RECOVERY_OPERATIONS
    
    def execute_recovery(
        self,
        request: RecoveryOperationRequest
    ) -> RecoveryOperationResult:
        """
        Execute a recovery operation using Phase 12A contracts.

        This is the primary entry point for recovery operations that integrates
        with the Phase 12 contract system.
        
        Supported operations (local):
            - REVERT_DRAFT: Revert a draft to previous state using audit history
            - MANUAL_OVERRIDE: Admin override to set specific state
        
        Deferred operations (require Graph API):
            - RETRY_SEND: Retry a failed send operation
            - RESYNC_FROM_EXCEL: Re-sync draft from Excel authority
        
        Args:
            request: RecoveryOperationRequest with operation details
            
        Returns:
            RecoveryOperationResult with outcome and details
        """
        logger.info(
            f"Recovery requested: type={request.operation_type.value}, "
            f"target={request.target_id}, by={request.requested_by}"
        )
        
        # Check if operation is deferred (requires Graph API)
        if self.is_operation_deferred(request.operation_type):
            logger.warning(
                f"Recovery operation {request.operation_type.value} is deferred - "
                "requires Graph API credentials"
            )
            return RecoveryOperationResult(
                request=request,
                outcome=RecoveryOutcome.FAILED,
                message=(
                    f"Operation {request.operation_type.value} is deferred: "
                    "requires Graph API credentials which are not configured. "
                    "This operation will be available in Phase 12B."
                ),
                recovered_state=None,
            )
        
        # Route to appropriate handler
        try:
            if request.operation_type == RecoveryOperationType.REVERT_DRAFT:
                return self._execute_revert_draft(request)
            elif request.operation_type == RecoveryOperationType.MANUAL_OVERRIDE:
                return self._execute_manual_override(request)
            else:
                return RecoveryOperationResult(
                    request=request,
                    outcome=RecoveryOutcome.FAILED,
                    message=f"Unknown operation type: {request.operation_type.value}",
                )
        except Exception as e:
            logger.error(f"Recovery operation failed: {e}")
            return RecoveryOperationResult(
                request=request,
                outcome=RecoveryOutcome.FAILED,
                message=f"Recovery failed with error: {str(e)}",
            )
    
    def _execute_revert_draft(
        self,
        request: RecoveryOperationRequest
    ) -> RecoveryOperationResult:
        """
        Execute REVERT_DRAFT operation.
        
        Uses the existing point-in-time recovery to revert a draft
        to a previous state based on audit history.
        
        Expected metadata:
            - target_time: ISO timestamp to revert to (optional, defaults to last edit)
            - dry_run: If true, preview only (optional, defaults to false)
        """
        metadata = request.metadata or {}
        target_time_str = metadata.get("target_time")
        dry_run = metadata.get("dry_run", False)
        
        # Determine target time
        if target_time_str:
            try:
                target_time = datetime.fromisoformat(target_time_str)
            except ValueError:
                return RecoveryOperationResult(
                    request=request,
                    outcome=RecoveryOutcome.FAILED,
                    message=f"Invalid target_time format: {target_time_str}",
                )
        else:
            # Get the most recent recovery point and go back one step
            points = self.get_recovery_points(request.target_id, limit=2)
            if len(points) < 2:
                return RecoveryOperationResult(
                    request=request,
                    outcome=RecoveryOutcome.FAILED,
                    message="No previous state available to revert to",
                )
            # Target time is just before the most recent change
            target_time = points[1].timestamp
        
        # Execute recovery
        result = self.recover_to_point(
            receipt_id=request.target_id,
            target_time=target_time,
            dry_run=dry_run
        )
        
        if result.success:
            outcome = RecoveryOutcome.SUCCESS
            message = (
                f"Draft {request.target_id} {'would be' if dry_run else 'was'} "
                f"reverted to state at {target_time.isoformat()}"
            )
            if result.audit_trail:
                message += f" ({len(result.audit_trail)} changes reverted)"
        else:
            outcome = RecoveryOutcome.FAILED
            message = result.error_message or "Revert failed"
        
        return RecoveryOperationResult(
            request=request,
            outcome=outcome,
            message=message,
            recovered_state=result.recovered_data,
        )
    
    def _execute_manual_override(
        self,
        request: RecoveryOperationRequest
    ) -> RecoveryOperationResult:
        """
        Execute MANUAL_OVERRIDE operation.
        
        Allows admin to directly set draft state, bypassing normal recovery.
        
        Expected metadata:
            - new_state: Dict with field values to set
            - reason: Why the override is needed (required for audit)
        """
        metadata = request.metadata or {}
        new_state = metadata.get("new_state")
        override_reason = request.reason or metadata.get("reason", "No reason provided")
        
        if not new_state or not isinstance(new_state, dict):
            return RecoveryOperationResult(
                request=request,
                outcome=RecoveryOutcome.FAILED,
                message="MANUAL_OVERRIDE requires 'new_state' dict in metadata",
            )
        
        conn = self._get_connection()
        try:
            # Verify draft exists
            cursor = conn.execute(
                "SELECT receipt_data FROM drafts WHERE id = ?",
                (request.target_id,)
            )
            row = cursor.fetchone()
            if not row:
                return RecoveryOperationResult(
                    request=request,
                    outcome=RecoveryOutcome.FAILED,
                    message=f"Draft {request.target_id} not found",
                )
            
            # Get current state for audit
            current_data = row["receipt_data"]
            
            # Merge new_state into receipt_data
            try:
                receipt_data = json.loads(current_data) if current_data else {}
            except (json.JSONDecodeError, TypeError):
                receipt_data = {}
            
            receipt_data.update(new_state)
            
            # Update the draft
            conn.execute("""
                UPDATE drafts 
                SET receipt_data = ?,
                    updated_at = ?
                WHERE id = ?
            """, (json.dumps(receipt_data), datetime.utcnow().isoformat(), request.target_id))
            
            # Log the override in audit trail
            try:
                conn.execute("""
                    INSERT INTO post_send_edits (
                        edit_id, receipt_id, edited_at, field_name,
                        old_value, new_value, edited_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"override_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    request.target_id,
                    datetime.utcnow().isoformat(),
                    "_manual_override",
                    current_data,
                    json.dumps({"new_state": new_state, "reason": override_reason}),
                    request.requested_by
                ))
            except sqlite3.OperationalError:
                logger.warning("Could not log override to post_send_edits table")
            
            conn.commit()
            
            logger.info(
                f"Manual override applied to {request.target_id} by {request.requested_by}: "
                f"{override_reason}"
            )
            
            return RecoveryOperationResult(
                request=request,
                outcome=RecoveryOutcome.SUCCESS,
                message=f"Manual override applied to draft {request.target_id}",
                recovered_state=receipt_data,
            )
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Manual override failed: {e}")
            return RecoveryOperationResult(
                request=request,
                outcome=RecoveryOutcome.FAILED,
                message=f"Override failed: {str(e)}",
            )
        finally:
            conn.close()


# Module-level singleton
_recovery_service: Optional[DataRecoveryService] = None


def get_recovery_service(db_path: str = "app/Data/drafts.db") -> DataRecoveryService:
    """Get or create the singleton recovery service instance."""
    global _recovery_service
    if _recovery_service is None:
        _recovery_service = DataRecoveryService(db_path)
    return _recovery_service
