import copy
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

class SubmissionHistory:
    """Manage receipt submission history and analysis queue."""

    def __init__(self):
        self.analysis_queue: Dict[str, Dict[str, Any]] = {}
        self.submissions: List[Dict[str, Any]] = []
        self.analysis_cache: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()

    def create_pending_analysis(self, queue_id: str, metadata: Optional[str], payload_hash: Optional[str], preprocess_stats: Optional[Dict[str, Any]] = None):
        """Add a placeholder entry so clients can poll for status."""
        with self.lock:
            self.analysis_queue[queue_id] = {
                'analysis_data': None,
                'metadata': metadata,
                'payload_hash': payload_hash,
                'timestamp': datetime.now().isoformat(),
                'status': 'queued',
                'preprocess': preprocess_stats or {},
                'error': None
            }

    def mark_analysis_processing(self, queue_id: str):
        with self.lock:
            if queue_id in self.analysis_queue:
                self.analysis_queue[queue_id]['status'] = 'processing'
                self.analysis_queue[queue_id]['started_at'] = datetime.now().isoformat()

    def mark_analysis_failed(self, queue_id: str, error_message: str):
        with self.lock:
            if queue_id in self.analysis_queue:
                self.analysis_queue[queue_id]['status'] = 'failed'
                self.analysis_queue[queue_id]['error'] = error_message
                self.analysis_queue[queue_id]['completed_at'] = datetime.now().isoformat()

    def store_analysis(self, queue_id: str, analysis_data: Dict[str, Any], metadata: Optional[str] = None,
                       payload_hash: Optional[str] = None, timings: Optional[Dict[str, Any]] = None):
        """Store OCR analysis results for later submission."""
        record = {
            'analysis_data': analysis_data,
            'metadata': metadata,
            'payload_hash': payload_hash,
            'timestamp': datetime.now().isoformat(),
            'status': 'completed',
            'timings': timings or {}
        }

        with self.lock:
            self.analysis_queue[queue_id] = record
            if payload_hash:
                self.analysis_cache[payload_hash] = copy.deepcopy(analysis_data)

    def get_analysis(self, queue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored analysis by queue ID."""
        with self.lock:
            entry = self.analysis_queue.get(queue_id)
            if not entry:
                return None
            return entry.get('analysis_data')

    def get_analysis_status(self, queue_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            entry = self.analysis_queue.get(queue_id)
            if not entry:
                return None
            # Return a copy to avoid accidental mutation
            status_copy = copy.deepcopy(entry)
            return status_copy

    def get_cached_analysis(self, payload_hash: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            cached = self.analysis_cache.get(payload_hash)
            return copy.deepcopy(cached) if cached else None

    def store_submission(self, queue_id: str, verified_data: Dict[str, Any],
                        user_data: Dict[str, Any], excel_path: str):
        """Store completed submission."""
        submission = {
            'queue_id': queue_id,
            'verified_data': verified_data,
            'user_data': user_data,
            'excel_path': excel_path,
            'excel_url': f"/artifacts/{Path(excel_path).name}",
            'thumbnail_url': f"data:image/jpeg;base64,{verified_data.get('thumbnail', '')}" if verified_data.get('thumbnail') else None,
            'timestamp': datetime.now().isoformat(),
            'status': 'submitted'
        }

        with self.lock:
            self.submissions.append(submission)
            if queue_id in self.analysis_queue:
                del self.analysis_queue[queue_id]

    def get_recent_submissions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent submissions for history display."""
        # Sort by timestamp (newest first) and limit results
        with self.lock:
            sorted_submissions = sorted(
                self.submissions,
                key=lambda x: x['timestamp'],
                reverse=True
            )[:limit]

        # Format for frontend display
        history_items = []
        for sub in sorted_submissions:
            data = sub['verified_data']
            user = sub['user_data']

            item = {
                'id': sub['queue_id'],
                'vendor': data.get('vendor', 'Unknown Vendor'),
                'total': data.get('total', '0'),
                'currency': data.get('currency', 'JPY'),
                'date': data.get('date', ''),
                'timestamp': sub['timestamp'],
                'verified': True,  # All submitted items are verified
                'excel_url': sub.get('excel_url'),
                'thumbnail_url': sub.get('thumbnail_url'),
                'user_name': user.get('name', ''),
                'user_email': user.get('email', '')
            }
            history_items.append(item)

        return history_items

    def get_submission_count(self) -> int:
        """Get total number of submissions."""
        with self.lock:
            return len(self.submissions)

    def clear_old_analyses(self, hours: int = 24):
        """Clear old unprocessed analyses (optional cleanup)."""
        # Implementation for cleanup if needed
        pass