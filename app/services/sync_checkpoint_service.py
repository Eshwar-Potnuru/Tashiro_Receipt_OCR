"""
Phase 12B-2: Sync Checkpoint Service

Manages synchronization checkpoints for tracking Excel sync state.
Enables incremental sync by recording when and what was last synchronized.

Features:
    - Checkpoint creation, update, and retrieval
    - In-memory storage with optional file persistence
    - Composite key support (file_id + worksheet + optional row)
    - Hash-based comparison utilities
    - Thread-safe operations

Architecture:
    Checkpoint → records last-known sync state
                 ↓
    Polling → compare current vs checkpoint
              ↓
    Detection → determine if external change occurred

This implementation is:
    - Environment-independent (no live Graph calls)
    - Polling-friendly (designed for periodic checks)
    - Deterministic (consistent results given same inputs)

Author: Phase 12B-2
Date: 2026-03-28
"""

import hashlib
import json
import logging
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.phase12_contracts import (
    SyncCheckpoint,
    SyncDirection,
    ISyncCheckpointService,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CHECKPOINT KEY GENERATION
# =============================================================================

def make_checkpoint_key(
    file_id: str,
    worksheet_name: Optional[str] = None,
    row_index: Optional[int] = None
) -> str:
    """Generate a composite key for checkpoint storage.
    
    Args:
        file_id: OneDrive file ID
        worksheet_name: Optional worksheet name
        row_index: Optional row index for row-level tracking
        
    Returns:
        Composite key string
        
    Example:
        >>> make_checkpoint_key("abc123", "2026年3月")
        "abc123::2026年3月"
        >>> make_checkpoint_key("abc123", "2026年3月", 42)
        "abc123::2026年3月::row_42"
    """
    parts = [file_id]
    if worksheet_name:
        parts.append(worksheet_name)
    if row_index is not None:
        parts.append(f"row_{row_index}")
    return "::".join(parts)


def parse_checkpoint_key(key: str) -> Dict[str, Any]:
    """Parse a composite checkpoint key back to components.
    
    Args:
        key: Composite key string
        
    Returns:
        Dictionary with file_id, worksheet_name, row_index
    """
    parts = key.split("::")
    result = {"file_id": parts[0], "worksheet_name": None, "row_index": None}
    
    if len(parts) >= 2:
        result["worksheet_name"] = parts[1]
    if len(parts) >= 3 and parts[2].startswith("row_"):
        result["row_index"] = int(parts[2].replace("row_", ""))
    
    return result


# =============================================================================
# HASH UTILITIES
# =============================================================================

def compute_checkpoint_hash(data: Dict[str, Any]) -> str:
    """Compute a deterministic hash for checkpoint comparison.
    
    Args:
        data: Dictionary of values to hash
        
    Returns:
        SHA-256 hash string (first 16 chars)
    """
    # Sort keys for deterministic ordering
    normalized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# =============================================================================
# CHECKPOINT SERVICE IMPLEMENTATION
# =============================================================================

class SyncCheckpointService(ISyncCheckpointService):
    """
    Service for managing sync checkpoints.
    
    Implements ISyncCheckpointService interface from Phase 12B contracts.
    Provides in-memory storage with optional file persistence.
    
    Thread-safe for concurrent access.
    
    Usage:
        service = SyncCheckpointService()
        
        # Create a checkpoint after syncing
        checkpoint = service.create_checkpoint(
            file_id="abc123",
            worksheet_name="2026年3月",
            etag="W/\"abc...\"",
            row_hash="xyz789...",
            sync_direction=SyncDirection.APP_TO_EXCEL
        )
        
        # Retrieve later
        existing = service.get_checkpoint("abc123")
        
        # Update after next sync
        service.update_checkpoint_etag("abc123", "W/\"new...\"")
    """
    
    def __init__(
        self,
        persistence_path: Optional[Path] = None,
        auto_persist: bool = False
    ):
        """
        Initialize the checkpoint service.
        
        Args:
            persistence_path: Optional path for file-based persistence
            auto_persist: If True, auto-save after each modification
        """
        self._checkpoints: Dict[str, SyncCheckpoint] = {}
        self._lock = threading.RLock()
        self._persistence_path = persistence_path
        self._auto_persist = auto_persist
        self._modification_count = 0
        
        # Load from persistence if available
        if persistence_path and persistence_path.exists():
            self._load_from_file()
        
        logger.info(
            f"SyncCheckpointService initialized "
            f"(persistence={'enabled' if persistence_path else 'disabled'})"
        )
    
    # -------------------------------------------------------------------------
    # INTERFACE IMPLEMENTATION (ISyncCheckpointService)
    # -------------------------------------------------------------------------
    
    def get_checkpoint(self, file_id: str) -> Optional[SyncCheckpoint]:
        """Get checkpoint by file_id (interface method).
        
        Args:
            file_id: OneDrive file ID
            
        Returns:
            SyncCheckpoint or None if not found
        """
        key = make_checkpoint_key(file_id)
        return self.get_checkpoint_by_key(key)
    
    def save_checkpoint(self, checkpoint: SyncCheckpoint) -> None:
        """Save a checkpoint (interface method).
        
        Args:
            checkpoint: Checkpoint to save
        """
        key = make_checkpoint_key(
            checkpoint.file_id,
            checkpoint.worksheet_name
        )
        self._store_checkpoint(key, checkpoint)
    
    # -------------------------------------------------------------------------
    # EXTENDED API
    # -------------------------------------------------------------------------
    
    def create_checkpoint(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        etag: Optional[str] = None,
        row_hash: Optional[str] = None,
        sync_direction: Optional[SyncDirection] = None,
        row_index: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SyncCheckpoint:
        """Create a new checkpoint and store it.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            etag: Current ETag of the file
            row_hash: Hash of row data
            sync_direction: Direction of sync
            row_index: Optional row index for row-level tracking
            metadata: Additional metadata
            
        Returns:
            Created SyncCheckpoint
        """
        # Generate unique checkpoint ID
        checkpoint_id = f"cp_{file_id[:8]}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        checkpoint = SyncCheckpoint(
            checkpoint_id=checkpoint_id,
            file_id=file_id,
            worksheet_name=worksheet_name,
            last_synced_at=datetime.utcnow(),
            last_etag=etag,
            last_row_hash=row_hash,
            sync_direction=sync_direction,
            metadata=metadata or {}
        )
        
        # Add row_index to metadata if provided
        if row_index is not None:
            checkpoint.metadata = checkpoint.metadata or {}
            checkpoint.metadata["row_index"] = row_index
        
        key = make_checkpoint_key(file_id, worksheet_name, row_index)
        self._store_checkpoint(key, checkpoint)
        
        logger.debug(f"Created checkpoint: {checkpoint_id} for file {file_id[:8]}...")
        return checkpoint
    
    def get_checkpoint_by_key(self, key: str) -> Optional[SyncCheckpoint]:
        """Get checkpoint by composite key.
        
        Args:
            key: Composite checkpoint key
            
        Returns:
            SyncCheckpoint or None
        """
        with self._lock:
            return self._checkpoints.get(key)
    
    def get_checkpoint_for_file(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        row_index: Optional[int] = None
    ) -> Optional[SyncCheckpoint]:
        """Get checkpoint by file components.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            row_index: Optional row index
            
        Returns:
            SyncCheckpoint or None
        """
        key = make_checkpoint_key(file_id, worksheet_name, row_index)
        return self.get_checkpoint_by_key(key)
    
    def update_checkpoint(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        new_etag: Optional[str] = None,
        new_row_hash: Optional[str] = None,
        sync_direction: Optional[SyncDirection] = None,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[SyncCheckpoint]:
        """Update an existing checkpoint.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            new_etag: New ETag to record
            new_row_hash: New row hash to record
            sync_direction: New sync direction
            additional_metadata: Metadata to merge
            
        Returns:
            Updated SyncCheckpoint or None if not found
        """
        key = make_checkpoint_key(file_id, worksheet_name)
        
        with self._lock:
            existing = self._checkpoints.get(key)
            if not existing:
                logger.warning(f"Checkpoint not found for update: {key}")
                return None
            
            # Update fields
            existing.last_synced_at = datetime.utcnow()
            if new_etag is not None:
                existing.last_etag = new_etag
            if new_row_hash is not None:
                existing.last_row_hash = new_row_hash
            if sync_direction is not None:
                existing.sync_direction = sync_direction
            if additional_metadata:
                existing.metadata = existing.metadata or {}
                existing.metadata.update(additional_metadata)
            
            self._checkpoints[key] = existing
            self._on_modification()
        
        logger.debug(f"Updated checkpoint: {existing.checkpoint_id}")
        return existing
    
    def update_checkpoint_etag(
        self,
        file_id: str,
        new_etag: str,
        worksheet_name: Optional[str] = None
    ) -> bool:
        """Convenience method to update just the ETag.
        
        Args:
            file_id: OneDrive file ID
            new_etag: New ETag value
            worksheet_name: Optional worksheet name
            
        Returns:
            True if updated, False if checkpoint not found
        """
        result = self.update_checkpoint(
            file_id=file_id,
            worksheet_name=worksheet_name,
            new_etag=new_etag
        )
        return result is not None
    
    def delete_checkpoint(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None,
        row_index: Optional[int] = None
    ) -> bool:
        """Delete a checkpoint.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            row_index: Optional row index
            
        Returns:
            True if deleted, False if not found
        """
        key = make_checkpoint_key(file_id, worksheet_name, row_index)
        
        with self._lock:
            if key in self._checkpoints:
                del self._checkpoints[key]
                self._on_modification()
                logger.debug(f"Deleted checkpoint: {key}")
                return True
        
        return False
    
    def list_checkpoints(
        self,
        file_id: Optional[str] = None
    ) -> List[SyncCheckpoint]:
        """List all checkpoints, optionally filtered by file_id.
        
        Args:
            file_id: Optional filter by file ID
            
        Returns:
            List of matching checkpoints
        """
        with self._lock:
            if file_id:
                return [
                    cp for cp in self._checkpoints.values()
                    if cp.file_id == file_id
                ]
            return list(self._checkpoints.values())
    
    def clear_all(self) -> int:
        """Clear all checkpoints.
        
        Returns:
            Number of checkpoints cleared
        """
        with self._lock:
            count = len(self._checkpoints)
            self._checkpoints.clear()
            self._on_modification()
        
        logger.info(f"Cleared {count} checkpoints")
        return count
    
    # -------------------------------------------------------------------------
    # COMPARISON UTILITIES
    # -------------------------------------------------------------------------
    
    def has_etag_changed(
        self,
        file_id: str,
        current_etag: str,
        worksheet_name: Optional[str] = None
    ) -> Optional[bool]:
        """Check if ETag has changed since checkpoint.
        
        Args:
            file_id: OneDrive file ID
            current_etag: Current ETag to compare
            worksheet_name: Optional worksheet name
            
        Returns:
            True if changed, False if same, None if no checkpoint
        """
        checkpoint = self.get_checkpoint_for_file(file_id, worksheet_name)
        if not checkpoint or not checkpoint.last_etag:
            return None  # Cannot determine - no baseline
        
        return checkpoint.last_etag != current_etag
    
    def has_hash_changed(
        self,
        file_id: str,
        current_hash: str,
        worksheet_name: Optional[str] = None
    ) -> Optional[bool]:
        """Check if row hash has changed since checkpoint.
        
        Args:
            file_id: OneDrive file ID
            current_hash: Current hash to compare
            worksheet_name: Optional worksheet name
            
        Returns:
            True if changed, False if same, None if no checkpoint
        """
        checkpoint = self.get_checkpoint_for_file(file_id, worksheet_name)
        if not checkpoint or not checkpoint.last_row_hash:
            return None  # Cannot determine - no baseline
        
        return checkpoint.last_row_hash != current_hash
    
    def get_time_since_last_sync(
        self,
        file_id: str,
        worksheet_name: Optional[str] = None
    ) -> Optional[float]:
        """Get seconds since last sync.
        
        Args:
            file_id: OneDrive file ID
            worksheet_name: Optional worksheet name
            
        Returns:
            Seconds since last sync, or None if no checkpoint
        """
        checkpoint = self.get_checkpoint_for_file(file_id, worksheet_name)
        if not checkpoint or not checkpoint.last_synced_at:
            return None
        
        delta = datetime.utcnow() - checkpoint.last_synced_at
        return delta.total_seconds()
    
    # -------------------------------------------------------------------------
    # PERSISTENCE
    # -------------------------------------------------------------------------
    
    def persist(self) -> bool:
        """Persist checkpoints to file.
        
        Returns:
            True if persisted successfully, False otherwise
        """
        if not self._persistence_path:
            logger.warning("No persistence path configured")
            return False
        
        try:
            with self._lock:
                data = {
                    "version": "1.0",
                    "saved_at": datetime.utcnow().isoformat(),
                    "checkpoints": {
                        key: self._checkpoint_to_dict(cp)
                        for key, cp in self._checkpoints.items()
                    }
                }
            
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            
            logger.info(f"Persisted {len(self._checkpoints)} checkpoints")
            return True
            
        except Exception as e:
            logger.error(f"Failed to persist checkpoints: {e}")
            return False
    
    def _load_from_file(self) -> bool:
        """Load checkpoints from persistence file."""
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            checkpoints_data = data.get("checkpoints", {})
            
            with self._lock:
                for key, cp_data in checkpoints_data.items():
                    self._checkpoints[key] = self._dict_to_checkpoint(cp_data)
            
            logger.info(f"Loaded {len(self._checkpoints)} checkpoints from file")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load checkpoints: {e}")
            return False
    
    def _checkpoint_to_dict(self, checkpoint: SyncCheckpoint) -> Dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "file_id": checkpoint.file_id,
            "worksheet_name": checkpoint.worksheet_name,
            "last_synced_at": checkpoint.last_synced_at.isoformat() if checkpoint.last_synced_at else None,
            "last_etag": checkpoint.last_etag,
            "last_row_hash": checkpoint.last_row_hash,
            "sync_direction": checkpoint.sync_direction.value if checkpoint.sync_direction else None,
            "metadata": checkpoint.metadata,
        }
    
    def _dict_to_checkpoint(self, data: Dict[str, Any]) -> SyncCheckpoint:
        """Convert dictionary to checkpoint."""
        last_synced = data.get("last_synced_at")
        if last_synced and isinstance(last_synced, str):
            last_synced = datetime.fromisoformat(last_synced)
        
        sync_dir = data.get("sync_direction")
        if sync_dir:
            sync_dir = SyncDirection(sync_dir)
        
        return SyncCheckpoint(
            checkpoint_id=data["checkpoint_id"],
            file_id=data["file_id"],
            worksheet_name=data.get("worksheet_name"),
            last_synced_at=last_synced,
            last_etag=data.get("last_etag"),
            last_row_hash=data.get("last_row_hash"),
            sync_direction=sync_dir,
            metadata=data.get("metadata"),
        )
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    
    def _store_checkpoint(self, key: str, checkpoint: SyncCheckpoint) -> None:
        """Store a checkpoint with thread safety."""
        with self._lock:
            self._checkpoints[key] = checkpoint
            self._on_modification()
    
    def _on_modification(self) -> None:
        """Called after each modification."""
        self._modification_count += 1
        if self._auto_persist and self._persistence_path:
            self.persist()
    
    @property
    def checkpoint_count(self) -> int:
        """Number of checkpoints currently stored."""
        with self._lock:
            return len(self._checkpoints)
    
    @property
    def modification_count(self) -> int:
        """Total number of modifications since initialization."""
        return self._modification_count


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_sync_checkpoint_service: Optional[SyncCheckpointService] = None
_service_lock = threading.Lock()


def get_sync_checkpoint_service(
    persistence_path: Optional[Path] = None
) -> SyncCheckpointService:
    """Get the singleton SyncCheckpointService instance.
    
    Args:
        persistence_path: Optional path for persistence (only used on first call)
        
    Returns:
        SyncCheckpointService singleton instance
    """
    global _sync_checkpoint_service
    
    with _service_lock:
        if _sync_checkpoint_service is None:
            _sync_checkpoint_service = SyncCheckpointService(
                persistence_path=persistence_path
            )
    
    return _sync_checkpoint_service


def reset_sync_checkpoint_service() -> None:
    """Reset the singleton (for testing)."""
    global _sync_checkpoint_service
    with _service_lock:
        _sync_checkpoint_service = None
