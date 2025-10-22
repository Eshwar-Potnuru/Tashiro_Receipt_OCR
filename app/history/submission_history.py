import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

class SubmissionHistory:
    """Manage receipt submission history and analysis queue."""

    def __init__(self):
        self.analysis_queue = {}  # queue_id -> analysis_data
        self.submissions = []     # List of completed submissions

    def store_analysis(self, queue_id: str, analysis_data: Dict[str, Any], metadata: Optional[str] = None):
        """Store OCR analysis results for later submission."""
        self.analysis_queue[queue_id] = {
            'analysis_data': analysis_data,
            'metadata': metadata,
            'timestamp': datetime.now().isoformat(),
            'status': 'analyzed'
        }

    def get_analysis(self, queue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored analysis by queue ID."""
        return self.analysis_queue.get(queue_id, {}).get('analysis_data')

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

        self.submissions.append(submission)

        # Remove from analysis queue
        if queue_id in self.analysis_queue:
            del self.analysis_queue[queue_id]

    def get_recent_submissions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent submissions for history display."""
        # Sort by timestamp (newest first) and limit results
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
        return len(self.submissions)

    def clear_old_analyses(self, hours: int = 24):
        """Clear old unprocessed analyses (optional cleanup)."""
        # Implementation for cleanup if needed
        pass