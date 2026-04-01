"""
Excel Sync Detection Service (Phase 10 Foundation)

Polling-based detection of direct OneDrive/Excel edits.
Monitors for changes made outside the application (e.g., via Excel Online or Excel Desktop).

Features:
    - Periodic ETag polling to detect external modifications
    - Change event dispatching
    - Conflict detection and flagging
    - Audit trail of external modifications

Author: Phase 10 Foundation
Date: 2025-01-24
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SyncEventType(Enum):
    """Types of sync events detected."""
    EXTERNAL_MODIFICATION = "external_modification"
    FILE_DELETED = "file_deleted"
    FILE_CREATED = "file_created"
    PERMISSION_CHANGED = "permission_changed"
    CONFLICT_DETECTED = "conflict_detected"


@dataclass
class SyncEvent:
    """Represents a detected sync event."""
    event_type: SyncEventType
    file_id: str
    file_path: str
    timestamp: datetime
    old_etag: Optional[str] = None
    new_etag: Optional[str] = None
    detected_by: str = "polling"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/API response."""
        return {
            "event_type": self.event_type.value,
            "file_id": self.file_id,
            "file_path": self.file_path,
            "timestamp": self.timestamp.isoformat(),
            "old_etag": self.old_etag,
            "new_etag": self.new_etag,
            "detected_by": self.detected_by,
            "metadata": self.metadata
        }


@dataclass
class TrackedFile:
    """Information about a file being tracked for changes."""
    file_id: str
    file_path: str
    last_known_etag: str
    last_checked: datetime
    last_modified_by_app: datetime
    check_count: int = 0
    external_modification_count: int = 0


class ExcelSyncDetector:
    """
    Detects external modifications to Excel files in OneDrive.
    
    Uses ETag polling to identify when files have been modified outside
    the application, enabling conflict detection and proper handling.
    
    Usage:
        detector = ExcelSyncDetector(graph_client)
        detector.track_file(file_id, file_path, current_etag)
        await detector.start_polling()
        
        # Register event handlers
        detector.on_change(my_handler_function)
    """
    
    def __init__(
        self,
        graph_client: Any = None,
        poll_interval_seconds: int = 30,
        max_tracked_files: int = 1000
    ):
        """
        Initialize the sync detector.
        
        Args:
            graph_client: Microsoft Graph API client instance
            poll_interval_seconds: Seconds between poll cycles
            max_tracked_files: Maximum number of files to track
        """
        self._graph_client = graph_client
        self._poll_interval = poll_interval_seconds
        self._max_tracked_files = max_tracked_files
        
        # File tracking state
        self._tracked_files: Dict[str, TrackedFile] = {}
        self._event_handlers: List[Callable[[SyncEvent], None]] = []
        self._async_event_handlers: List[Callable[[SyncEvent], Any]] = []
        
        # Polling state
        self._polling_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._last_poll_time: Optional[datetime] = None
        self._poll_count = 0
        self._error_count = 0
        
        # Event history (limited)
        self._recent_events: List[SyncEvent] = []
        self._max_event_history = 100
        
        logger.info(f"ExcelSyncDetector initialized (poll_interval={poll_interval_seconds}s)")
    
    def set_graph_client(self, graph_client: Any) -> None:
        """Set or update the Graph API client."""
        self._graph_client = graph_client
        logger.debug("Graph client updated")
    
    def track_file(
        self,
        file_id: str,
        file_path: str,
        current_etag: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Start tracking a file for external modifications.
        
        Args:
            file_id: OneDrive file ID
            file_path: Path for logging/display
            current_etag: Current ETag of the file
            metadata: Optional additional metadata
            
        Returns:
            True if tracking started, False if limit reached
        """
        if len(self._tracked_files) >= self._max_tracked_files and file_id not in self._tracked_files:
            logger.warning(f"Tracking limit reached ({self._max_tracked_files}), cannot track {file_path}")
            return False
        
        now = datetime.utcnow()
        self._tracked_files[file_id] = TrackedFile(
            file_id=file_id,
            file_path=file_path,
            last_known_etag=current_etag,
            last_checked=now,
            last_modified_by_app=now
        )
        
        logger.debug(f"Now tracking file: {file_path} (id={file_id[:8]}...)")
        return True
    
    def untrack_file(self, file_id: str) -> bool:
        """
        Stop tracking a file.
        
        Args:
            file_id: OneDrive file ID
            
        Returns:
            True if file was being tracked
        """
        if file_id in self._tracked_files:
            file_info = self._tracked_files.pop(file_id)
            logger.debug(f"Stopped tracking: {file_info.file_path}")
            return True
        return False
    
    def update_etag(self, file_id: str, new_etag: str) -> None:
        """
        Update the known ETag after an app-initiated write.
        
        Call this after the app successfully writes to a file to prevent
        false positive "external modification" events.
        
        Args:
            file_id: OneDrive file ID
            new_etag: New ETag from write response
        """
        if file_id in self._tracked_files:
            tracked = self._tracked_files[file_id]
            tracked.last_known_etag = new_etag
            tracked.last_modified_by_app = datetime.utcnow()
            logger.debug(f"Updated ETag for {tracked.file_path}")
    
    def on_change(self, handler: Callable[[SyncEvent], None]) -> None:
        """
        Register a synchronous handler for change events.
        
        Args:
            handler: Function to call when a change is detected
        """
        self._event_handlers.append(handler)
    
    def on_change_async(self, handler: Callable[[SyncEvent], Any]) -> None:
        """
        Register an async handler for change events.
        
        Args:
            handler: Async function to call when a change is detected
        """
        self._async_event_handlers.append(handler)
    
    async def start_polling(self) -> None:
        """Start the background polling task."""
        if self._is_running:
            logger.warning("Polling already running")
            return
        
        self._is_running = True
        self._polling_task = asyncio.create_task(self._poll_loop())
        logger.info("Sync detection polling started")
    
    async def stop_polling(self) -> None:
        """Stop the background polling task."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
        logger.info("Sync detection polling stopped")
    
    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._is_running:
            try:
                await self._poll_all_files()
                self._poll_count += 1
                self._last_poll_time = datetime.utcnow()
            except Exception as e:
                self._error_count += 1
                logger.error(f"Poll cycle error: {e}")
            
            await asyncio.sleep(self._poll_interval)
    
    async def _poll_all_files(self) -> None:
        """Poll all tracked files for changes."""
        if not self._graph_client:
            logger.debug("No graph client, skipping poll")
            return
        
        if not self._tracked_files:
            return
        
        # Create a copy to avoid modification during iteration
        files_to_check = list(self._tracked_files.values())
        
        for tracked in files_to_check:
            try:
                await self._check_file(tracked)
            except Exception as e:
                logger.error(f"Error checking file {tracked.file_path}: {e}")
    
    async def _check_file(self, tracked: TrackedFile) -> None:
        """
        Check a single file for changes.
        
        Args:
            tracked: TrackedFile to check
        """
        tracked.check_count += 1
        
        # Get current file metadata from Graph API
        try:
            metadata = await self._get_file_metadata(tracked.file_id)
        except FileNotFoundError:
            # File was deleted
            event = SyncEvent(
                event_type=SyncEventType.FILE_DELETED,
                file_id=tracked.file_id,
                file_path=tracked.file_path,
                timestamp=datetime.utcnow(),
                old_etag=tracked.last_known_etag
            )
            await self._dispatch_event(event)
            self.untrack_file(tracked.file_id)
            return
        except Exception as e:
            logger.warning(f"Failed to get metadata for {tracked.file_path}: {e}")
            return
        
        current_etag = metadata.get("eTag") or metadata.get("cTag")
        if not current_etag:
            logger.warning(f"No ETag in metadata for {tracked.file_path}")
            return
        
        tracked.last_checked = datetime.utcnow()
        
        # Check if ETag changed
        if current_etag != tracked.last_known_etag:
            # Check if this was a recent app-initiated change
            time_since_app_write = datetime.utcnow() - tracked.last_modified_by_app
            if time_since_app_write < timedelta(seconds=5):
                # Recent app write, might be propagation delay - update ETag
                tracked.last_known_etag = current_etag
                return
            
            # External modification detected
            tracked.external_modification_count += 1
            old_etag = tracked.last_known_etag
            tracked.last_known_etag = current_etag
            
            event = SyncEvent(
                event_type=SyncEventType.EXTERNAL_MODIFICATION,
                file_id=tracked.file_id,
                file_path=tracked.file_path,
                timestamp=datetime.utcnow(),
                old_etag=old_etag,
                new_etag=current_etag,
                metadata={
                    "last_modified_date_time": metadata.get("lastModifiedDateTime"),
                    "modified_by": metadata.get("lastModifiedBy", {}).get("user", {}).get("displayName")
                }
            )
            await self._dispatch_event(event)
    
    async def _get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Get file metadata from Graph API.
        
        Args:
            file_id: OneDrive file ID
            
        Returns:
            File metadata dict
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not self._graph_client:
            raise RuntimeError("No graph client available")
        
        # Use the graph client's get method
        try:
            response = await self._graph_client.get(f"/me/drive/items/{file_id}")
            if response.get("error"):
                error_code = response.get("error", {}).get("code", "")
                if error_code == "itemNotFound":
                    raise FileNotFoundError(f"File {file_id} not found")
                raise RuntimeError(response.get("error", {}).get("message", "Unknown error"))
            return response
        except Exception as e:
            if "404" in str(e) or "itemNotFound" in str(e):
                raise FileNotFoundError(f"File {file_id} not found")
            raise
    
    async def _dispatch_event(self, event: SyncEvent) -> None:
        """
        Dispatch a sync event to all registered handlers.
        
        Args:
            event: The event to dispatch
        """
        # Record in history
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_event_history:
            self._recent_events = self._recent_events[-self._max_event_history:]
        
        logger.info(f"Sync event: {event.event_type.value} for {event.file_path}")
        
        # Call sync handlers
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Sync event handler error: {e}")
        
        # Call async handlers
        for handler in self._async_event_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Async event handler error: {e}")
    
    def get_tracked_files(self) -> List[Dict[str, Any]]:
        """
        Get list of all tracked files and their status.
        
        Returns:
            List of tracked file info dicts
        """
        return [
            {
                "file_id": t.file_id,
                "file_path": t.file_path,
                "last_known_etag": t.last_known_etag,
                "last_checked": t.last_checked.isoformat() if t.last_checked else None,
                "check_count": t.check_count,
                "external_modification_count": t.external_modification_count
            }
            for t in self._tracked_files.values()
        ]
    
    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent sync events.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of event dicts, most recent first
        """
        events = self._recent_events[-limit:]
        return [e.to_dict() for e in reversed(events)]
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get detector status for monitoring.
        
        Returns:
            Status dict with polling state and statistics
        """
        return {
            "is_running": self._is_running,
            "poll_interval_seconds": self._poll_interval,
            "tracked_file_count": len(self._tracked_files),
            "max_tracked_files": self._max_tracked_files,
            "poll_count": self._poll_count,
            "error_count": self._error_count,
            "last_poll_time": self._last_poll_time.isoformat() if self._last_poll_time else None,
            "event_handler_count": len(self._event_handlers) + len(self._async_event_handlers),
            "recent_event_count": len(self._recent_events)
        }
    
    async def force_check(self, file_id: str) -> Optional[SyncEvent]:
        """
        Force an immediate check of a specific file.
        
        Args:
            file_id: OneDrive file ID to check
            
        Returns:
            SyncEvent if change detected, None otherwise
        """
        if file_id not in self._tracked_files:
            raise ValueError(f"File {file_id} is not being tracked")
        
        tracked = self._tracked_files[file_id]
        old_etag = tracked.last_known_etag
        
        await self._check_file(tracked)
        
        # Check if event was generated
        if self._recent_events and self._recent_events[-1].file_id == file_id:
            return self._recent_events[-1]
        return None


# Module-level singleton instance
_detector_instance: Optional[ExcelSyncDetector] = None


def get_sync_detector() -> ExcelSyncDetector:
    """Get or create the singleton sync detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = ExcelSyncDetector()
    return _detector_instance


def init_sync_detector(graph_client: Any, poll_interval: int = 30) -> ExcelSyncDetector:
    """
    Initialize the sync detector with a graph client.
    
    Args:
        graph_client: Microsoft Graph API client
        poll_interval: Seconds between poll cycles
        
    Returns:
        Initialized ExcelSyncDetector instance
    """
    global _detector_instance
    _detector_instance = ExcelSyncDetector(
        graph_client=graph_client,
        poll_interval_seconds=poll_interval
    )
    return _detector_instance
