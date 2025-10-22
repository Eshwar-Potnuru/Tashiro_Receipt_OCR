"""
HQ Server Integration Module (Placeholder)

This module will handle direct API communication with the Tashiro Ironworks HQ server
once API specifications are confirmed.

Current Status: Design phase - awaiting API availability confirmation
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class HQAPIClient:
    """
    Client for communicating with HQ server API.
    
    Currently a placeholder - will be implemented once API specs are available.
    """
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.enabled = False  # Will be enabled once API is ready
    
    async def submit_receipt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit a verified receipt to HQ server.
        
        Args:
            payload: Receipt data including user info, extracted fields, and category
            
        Returns:
            Response from HQ API including submission ID and status
            
        Raises:
            NotImplementedError: Until HQ API is available
        """
        if not self.enabled:
            logger.warning("HQ API not yet available - using file-based export fallback")
            raise NotImplementedError("HQ API integration pending - see docs/HQ_INTEGRATION.md")
        
        # TODO: Implement when API specs are available
        # - Add authentication headers
        # - POST to HQ endpoint
        # - Handle response/errors
        # - Implement retry logic
        pass
    
    async def check_status(self, submission_id: str) -> Dict[str, Any]:
        """
        Check the status of a submitted receipt.
        
        Args:
            submission_id: Unique ID of the submission
            
        Returns:
            Current status of the submission in HQ workflow
            
        Raises:
            NotImplementedError: Until HQ API is available
        """
        if not self.enabled:
            raise NotImplementedError("HQ API integration pending")
        
        # TODO: Implement status polling
        pass


def export_for_manual_transfer(
    submission_data: Dict[str, Any],
    export_path: str
) -> str:
    """
    Export submission to file for manual/batch transfer to HQ.
    
    This is the fallback method when API is unavailable.
    
    Args:
        submission_data: Complete receipt submission data
        export_path: Directory path for export files
        
    Returns:
        Path to the exported file
    """
    from datetime import datetime
    from pathlib import Path
    import json
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    submission_id = submission_data.get("submission_id", "unknown")
    filename = f"receipt_{timestamp}_{submission_id}.json"
    
    output_path = Path(export_path) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(submission_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Exported submission to {output_path} for manual transfer")
    return str(output_path)
