"""
Graph API Client Module (Phase 9A.1, Updated in 9A.4)

This module provides a base HTTP client for Microsoft Graph API operations.
It handles authentication, request building, error handling, retries, and
rate limiting.

Usage:
    from app.services.graph_client import graph_get, graph_post, graph_patch
    
    # Get user's drive info (with automatic retry)
    drive = graph_get("me/drive")
    
    # Create a folder (through request queue)
    folder = graph_post("me/drive/root/children", {
        "name": "NewFolder",
        "folder": {}
    })
    
    # Use resilient wrapper for full protection
    from app.services.graph_client import graph_request_resilient
    result = graph_request_resilient("GET", "me/drive")

Features:
    - Automatic token management via graph_auth module
    - Standardized error handling
    - Convenience wrappers for common HTTP methods
    - JSON serialization/deserialization
    - Retry with exponential backoff (Phase 9A.4)
    - Request queue with rate limiting (Phase 9A.4)
    - Health monitoring (Phase 9A.4)

Author: Phase 9A.1 - Graph API Foundation
Updated: Phase 9A.4 - Request Queue, Rate Limiting & Retry Engine
Date: 2026-02-28
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
import requests

from app.services.graph_auth import get_access_token

# Configure logging
logger = logging.getLogger(__name__)

# Microsoft Graph API base URL
GRAPH_API_BASE_URL = "https://graph.microsoft.com/v1.0"

# Default request timeout in seconds
DEFAULT_TIMEOUT = 30


class GraphAPIError(Exception):
    """
    Custom exception for Microsoft Graph API errors.
    
    Attributes:
        status_code: HTTP status code
        error_code: Graph API error code (e.g., 'itemNotFound')
        message: Human-readable error message
        request_id: Graph API request ID for debugging
    """
    
    def __init__(
        self,
        message: str,
        status_code: int = None,
        error_code: str = None,
        request_id: str = None,
        response_body: dict = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        self.response_body = response_body
    
    def __str__(self):
        parts = [self.message]
        if self.status_code:
            parts.append(f"[HTTP {self.status_code}]")
        if self.error_code:
            parts.append(f"[{self.error_code}]")
        if self.request_id:
            parts.append(f"(request-id: {self.request_id})")
        return " ".join(parts)


def _build_url(endpoint: str) -> str:
    """
    Build full Graph API URL from endpoint.
    
    Args:
        endpoint: API endpoint (e.g., "me/drive" or "/me/drive")
        
    Returns:
        Full URL including base URL
    """
    # Remove leading slash if present
    endpoint = endpoint.lstrip("/")
    return f"{GRAPH_API_BASE_URL}/{endpoint}"


def _get_headers() -> Dict[str, str]:
    """
    Get HTTP headers for Graph API request.
    
    Returns:
        Dict with Authorization and Content-Type headers
    """
    token = get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


def _parse_error_response(response: requests.Response) -> Dict[str, Any]:
    """
    Parse error details from Graph API response.
    
    Args:
        response: Response object from failed request
        
    Returns:
        Dict with error details
    """
    try:
        body = response.json()
        error = body.get("error", {})
        return {
            "error_code": error.get("code", "unknown"),
            "message": error.get("message", response.text),
            "request_id": response.headers.get("request-id"),
            "body": body
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "error_code": "parse_error",
            "message": response.text or f"HTTP {response.status_code}",
            "request_id": response.headers.get("request-id"),
            "body": None
        }


def graph_request(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a request to Microsoft Graph API.
    
    This is the base function that handles authentication, request building,
    and error handling for all Graph API calls.
    
    Args:
        method: HTTP method (GET, POST, PATCH, PUT, DELETE)
        endpoint: API endpoint (e.g., "users/{user-id}/drive")
        body: Optional request body (will be JSON serialized)
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response as dict. Returns empty dict for 204 No Content.
        
    Raises:
        GraphAPIError: If the request fails
        
    Example:
        # GET request
        result = graph_request("GET", "me/drive")
        
        # POST request with body
        result = graph_request("POST", "me/drive/root/children", {
            "name": "MyFolder",
            "folder": {}
        })
    """
    url = _build_url(endpoint)
    headers = _get_headers()
    
    logger.debug(f"Graph API {method} {endpoint}")
    
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=body if body else None,
            timeout=timeout
        )
        
        # Log request completion
        logger.debug(f"Graph API response: {response.status_code}")
        
        # Handle successful responses
        if response.status_code in (200, 201, 202):
            return response.json()
        
        # Handle 204 No Content (successful but no body)
        if response.status_code == 204:
            return {}
        
        # Handle error responses
        error_info = _parse_error_response(response)
        
        logger.error(
            f"Graph API error: {method} {endpoint} - "
            f"HTTP {response.status_code} - {error_info['error_code']}: {error_info['message']}"
        )
        
        raise GraphAPIError(
            message=error_info["message"],
            status_code=response.status_code,
            error_code=error_info["error_code"],
            request_id=error_info["request_id"],
            response_body=error_info["body"]
        )
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Graph API timeout: {method} {endpoint}")
        raise GraphAPIError(
            message=f"Request timed out after {timeout}s",
            error_code="timeout"
        ) from e
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Graph API connection error: {method} {endpoint}")
        raise GraphAPIError(
            message="Failed to connect to Microsoft Graph API",
            error_code="connection_error"
        ) from e
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Graph API request error: {method} {endpoint} - {str(e)}")
        raise GraphAPIError(
            message=f"Request failed: {str(e)}",
            error_code="request_error"
        ) from e


def graph_get(endpoint: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    Make a GET request to Microsoft Graph API.
    
    Args:
        endpoint: API endpoint (e.g., "me/drive")
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response
        
    Example:
        drive = graph_get("me/drive")
        print(drive["name"])
    """
    return graph_request("GET", endpoint, timeout=timeout)


def graph_post(
    endpoint: str,
    body: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a POST request to Microsoft Graph API.
    
    Args:
        endpoint: API endpoint
        body: Request body (will be JSON serialized)
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response
        
    Example:
        folder = graph_post("me/drive/root/children", {
            "name": "NewFolder",
            "folder": {}
        })
    """
    return graph_request("POST", endpoint, body=body, timeout=timeout)


def graph_patch(
    endpoint: str,
    body: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a PATCH request to Microsoft Graph API.
    
    Args:
        endpoint: API endpoint
        body: Request body with fields to update
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response
        
    Example:
        updated = graph_patch("me/drive/items/{item-id}", {
            "name": "RenamedFile.xlsx"
        })
    """
    return graph_request("PATCH", endpoint, body=body, timeout=timeout)


def graph_put(
    endpoint: str,
    body: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a PUT request to Microsoft Graph API.
    
    Args:
        endpoint: API endpoint
        body: Request body (complete resource)
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response
    """
    return graph_request("PUT", endpoint, body=body, timeout=timeout)


def graph_delete(endpoint: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    Make a DELETE request to Microsoft Graph API.
    
    Args:
        endpoint: API endpoint
        timeout: Request timeout in seconds
        
    Returns:
        Empty dict on success (204 No Content)
        
    Example:
        graph_delete("me/drive/items/{item-id}")
    """
    return graph_request("DELETE", endpoint, timeout=timeout)


def graph_request_with_etag(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    etag: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a Graph API request with optional ETag for optimistic concurrency.
    
    When an ETag is provided, sets the If-Match header to ensure the resource
    hasn't been modified since the ETag was obtained. If the resource has changed,
    the API returns 412 Precondition Failed.
    
    Args:
        method: HTTP method (POST, PATCH, PUT, DELETE)
        endpoint: API endpoint
        body: Optional request body
        etag: Optional ETag string for If-Match header
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (response_dict, new_etag) where new_etag may be None
        
    Raises:
        GraphAPIError: If request fails (including 412 for ETag mismatch)
    """
    url = _build_url(endpoint)
    headers = _get_headers()
    
    # Add If-Match header if ETag provided
    if etag:
        headers["If-Match"] = etag
    
    logger.debug(f"Graph API {method} {endpoint} (ETag: {'set' if etag else 'none'})")
    
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=body if body else None,
            timeout=timeout
        )
        
        # Extract new ETag from response headers
        new_etag = response.headers.get("ETag")
        
        logger.debug(f"Graph API response: {response.status_code}")
        
        # Handle successful responses
        if response.status_code in (200, 201, 202):
            result = response.json()
            # Also check for ETag in response body
            if not new_etag and isinstance(result, dict):
                new_etag = result.get("@odata.etag") or result.get("eTag")
            return {"data": result, "etag": new_etag}
        
        # Handle 204 No Content
        if response.status_code == 204:
            return {"data": {}, "etag": new_etag}
        
        # Handle error responses
        error_info = _parse_error_response(response)
        
        logger.error(
            f"Graph API error: {method} {endpoint} - "
            f"HTTP {response.status_code} - {error_info['error_code']}: {error_info['message']}"
        )
        
        raise GraphAPIError(
            message=error_info["message"],
            status_code=response.status_code,
            error_code=error_info["error_code"],
            request_id=error_info["request_id"],
            response_body=error_info["body"]
        )
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Graph API timeout: {method} {endpoint}")
        raise GraphAPIError(
            message=f"Request timed out after {timeout}s",
            error_code="timeout"
        ) from e
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Graph API connection error: {method} {endpoint}")
        raise GraphAPIError(
            message="Failed to connect to Microsoft Graph API",
            error_code="connection_error"
        ) from e
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Graph API request error: {method} {endpoint} - {str(e)}")
        raise GraphAPIError(
            message=f"Request failed: {str(e)}",
            error_code="request_error"
        ) from e


# Utility functions for common operations

def get_user_id() -> str:
    """
    Get the configured Microsoft user ID from environment.
    
    Phase 9 Step 2: Uses standardized placeholder detection.
    
    Returns:
        str: User ID or email from MICROSOFT_USER_ID env var
        
    Raises:
        ValueError: If MICROSOFT_USER_ID is not set or is a placeholder
    """
    from app.services.graph_auth import _is_placeholder_value
    
    user_id = os.environ.get("MICROSOFT_USER_ID")
    if _is_placeholder_value(user_id):
        raise ValueError(
            "MICROSOFT_USER_ID environment variable is not set or is a placeholder value. "
            "Set it to the OneDrive user's email or object ID."
        )
    return user_id


def get_base_folder() -> str:
    """
    Get the configured OneDrive base folder from environment.
    
    Phase 9 Step 2: Uses standardized placeholder detection.
    
    Returns:
        str: Base folder path from ONEDRIVE_BASE_FOLDER env var
        
    Raises:
        ValueError: If ONEDRIVE_BASE_FOLDER is not set or is a placeholder
    """
    from app.services.graph_auth import _is_placeholder_value
    
    folder = os.environ.get("ONEDRIVE_BASE_FOLDER")
    if _is_placeholder_value(folder):
        raise ValueError(
            "ONEDRIVE_BASE_FOLDER environment variable is not set or is a placeholder value. "
            "Set it to the OneDrive folder path (e.g., 'ReceiptOCR')."
        )
    return folder


# ============================================================================
# Phase 9A.4 - Resilient Request Functions
# ============================================================================

def graph_request_with_retry(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 4,
    operation_name: str = None
) -> Dict[str, Any]:
    """
    Make a Graph API request with automatic retry on transient failures.
    
    Uses exponential backoff with jitter. Automatically retries on:
        - 429 Too Many Requests (respects Retry-After)
        - 502, 503, 504 Service errors
        - Network timeouts and connection errors
    
    Args:
        method: HTTP method
        endpoint: API endpoint
        body: Optional request body
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts (default: 4)
        operation_name: Optional operation name for logging
        
    Returns:
        Parsed JSON response
        
    Raises:
        RetryExhaustedError: If all retries fail
        GraphAPIError: For non-retryable errors
        
    Example:
        result = graph_request_with_retry("GET", "me/drive", max_retries=3)
    """
    from app.services.retry_engine import with_retry
    from app.services.graph_health_monitor import record_success, record_failure, record_throttle
    
    op_name = operation_name or f"{method} {endpoint}"
    start_time = time.time()
    
    def on_retry(attempt: int, error: Exception, delay_ms: int):
        """Callback for retry monitoring."""
        # Check if it's a throttle
        if isinstance(error, GraphAPIError) and error.status_code == 429:
            record_throttle()
    
    try:
        result = with_retry(
            fn=lambda: graph_request(method, endpoint, body, timeout),
            max_retries=max_retries,
            operation_name=op_name,
            on_retry=on_retry
        )
        
        # Record success
        response_time = (time.time() - start_time) * 1000
        record_success(response_time, op_name)
        
        return result
        
    except Exception as e:
        # Record failure
        response_time = (time.time() - start_time) * 1000
        error_code = e.error_code if isinstance(e, GraphAPIError) else type(e).__name__
        record_failure(response_time, op_name, error_code)
        raise


def graph_request_queued(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    priority: str = 'normal',
    wait: bool = True,
    queue_timeout: float = None
) -> Dict[str, Any]:
    """
    Make a Graph API request through the request queue.
    
    The queue limits concurrent requests and pauses on rate limiting.
    Use this for batch operations or when rate limiting is expected.
    
    Args:
        method: HTTP method
        endpoint: API endpoint
        body: Optional request body
        timeout: Request timeout in seconds
        priority: Queue priority ('high', 'normal', 'low')
        wait: Whether to wait for result (default: True)
        queue_timeout: Max time to wait for result if wait=True
        
    Returns:
        Parsed JSON response if wait=True, else Future
        
    Raises:
        QueueOverflowError: If queue full and low priority
        TimeoutError: If wait times out
        GraphAPIError: For API errors
        
    Example:
        # High priority request
        result = graph_request_queued("GET", "me/drive", priority='high')
        
        # Low priority batch item
        result = graph_request_queued("GET", "users/list", priority='low')
    """
    from app.services.request_queue import enqueue
    
    return enqueue(
        request_fn=lambda: graph_request(method, endpoint, body, timeout),
        priority=priority,
        wait=wait,
        timeout=queue_timeout
    )


def graph_request_resilient(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 4,
    priority: str = 'normal',
    operation_name: str = None
) -> Dict[str, Any]:
    """
    Make a fully resilient Graph API request.
    
    Combines queue management, retry logic, and health monitoring for
    maximum reliability. This is the recommended function for production use.
    
    Pipeline:
        1. Request goes through queue (rate limiting, concurrency control)
        2. Retry wrapper handles transient failures
        3. Health monitor tracks success/failure/throttle
    
    Args:
        method: HTTP method
        endpoint: API endpoint
        body: Optional request body
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        priority: Queue priority ('high', 'normal', 'low')
        operation_name: Optional operation name for logging
        
    Returns:
        Parsed JSON response
        
    Raises:
        RetryExhaustedError: If all retries fail
        QueueOverflowError: If queue full
        GraphAPIError: For non-retryable errors
        
    Example:
        # Most reliable way to call Graph API
        result = graph_request_resilient("GET", "me/drive")
        
        # With custom settings
        result = graph_request_resilient(
            "PATCH", 
            f"me/drive/items/{item_id}",
            body={"name": "newname"},
            max_retries=3,
            priority='high'
        )
    """
    from app.services.request_queue import enqueue
    from app.services.retry_engine import with_retry
    from app.services.graph_health_monitor import (
        record_success, record_failure, record_throttle, is_circuit_open
    )
    
    op_name = operation_name or f"{method} {endpoint}"
    start_time = time.time()
    
    # Check circuit breaker
    if is_circuit_open():
        raise GraphAPIError(
            message="Graph API circuit breaker is open - too many consecutive failures",
            error_code="circuit_breaker_open"
        )
    
    def on_retry(attempt: int, error: Exception, delay_ms: int):
        """Callback for retry monitoring."""
        if isinstance(error, GraphAPIError) and error.status_code == 429:
            record_throttle()
    
    def make_request():
        """The actual request with retry logic."""
        return with_retry(
            fn=lambda: graph_request(method, endpoint, body, timeout),
            max_retries=max_retries,
            operation_name=op_name,
            on_retry=on_retry
        )
    
    try:
        # Go through queue
        result = enqueue(make_request, priority=priority, wait=True)
        
        # Record success
        response_time = (time.time() - start_time) * 1000
        record_success(response_time, op_name)
        
        return result
        
    except Exception as e:
        # Record failure
        response_time = (time.time() - start_time) * 1000
        error_code = e.error_code if isinstance(e, GraphAPIError) else type(e).__name__
        record_failure(response_time, op_name, error_code)
        raise


def graph_request_with_etag_resilient(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    etag: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 4,
    priority: str = 'high',
    operation_name: str = None
) -> Dict[str, Any]:
    """
    Make a resilient Graph API request with ETag support.
    
    Combines ETag-based optimistic concurrency with queue and retry.
    Use for write operations that need concurrency control.
    
    Args:
        method: HTTP method
        endpoint: API endpoint
        body: Optional request body
        etag: Optional ETag for If-Match header
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        priority: Queue priority (defaults to 'high' for writes)
        operation_name: Optional operation name for logging
        
    Returns:
        dict with 'data' (response) and 'etag' (new ETag)
        
    Raises:
        GraphAPIError: With status_code=412 for ETag mismatch
        RetryExhaustedError: If all retries fail
        
    Example:
        result = graph_request_with_etag_resilient(
            "PATCH",
            f"me/drive/items/{item_id}/workbook/worksheets/{ws}/range(address='A1')",
            body={"values": [["new value"]]},
            etag=current_etag
        )
        new_etag = result['etag']
    """
    from app.services.request_queue import enqueue
    from app.services.retry_engine import with_retry
    from app.services.graph_health_monitor import record_success, record_failure, record_throttle
    
    op_name = operation_name or f"{method} {endpoint}"
    start_time = time.time()
    
    def on_retry(attempt: int, error: Exception, delay_ms: int):
        if isinstance(error, GraphAPIError) and error.status_code == 429:
            record_throttle()
    
    def make_request():
        return with_retry(
            fn=lambda: graph_request_with_etag(method, endpoint, body, etag, timeout),
            max_retries=max_retries,
            operation_name=op_name,
            on_retry=on_retry,
            # Don't retry 412 ETag conflicts - let caller handle
            retry_on_status_codes=[429, 502, 503, 504]
        )
    
    try:
        result = enqueue(make_request, priority=priority, wait=True)
        
        response_time = (time.time() - start_time) * 1000
        record_success(response_time, op_name)
        
        return result
        
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        error_code = e.error_code if isinstance(e, GraphAPIError) else type(e).__name__
        record_failure(response_time, op_name, error_code)
        raise


# Resilient convenience wrappers

def graph_get_resilient(
    endpoint: str,
    timeout: int = DEFAULT_TIMEOUT,
    priority: str = 'normal'
) -> Dict[str, Any]:
    """Resilient GET request with queue, retry, and health monitoring."""
    return graph_request_resilient("GET", endpoint, timeout=timeout, priority=priority)


def graph_post_resilient(
    endpoint: str,
    body: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
    priority: str = 'normal'
) -> Dict[str, Any]:
    """Resilient POST request with queue, retry, and health monitoring."""
    return graph_request_resilient("POST", endpoint, body, timeout=timeout, priority=priority)


def graph_patch_resilient(
    endpoint: str,
    body: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
    priority: str = 'high'
) -> Dict[str, Any]:
    """Resilient PATCH request with queue, retry, and health monitoring."""
    return graph_request_resilient("PATCH", endpoint, body, timeout=timeout, priority=priority)


def graph_delete_resilient(
    endpoint: str,
    timeout: int = DEFAULT_TIMEOUT,
    priority: str = 'high'
) -> Dict[str, Any]:
    """Resilient DELETE request with queue, retry, and health monitoring."""
    return graph_request_resilient("DELETE", endpoint, timeout=timeout, priority=priority)


# =============================================================================
# PHASE 9 STEP 2: SAFE TEST OPERATIONS
# =============================================================================

def test_onedrive_access() -> dict:
    """
    Test OneDrive access without making any destructive operations.
    
    This is a SAFE, NON-DESTRUCTIVE operation that:
    1. Checks all required configuration is present
    2. Acquires a token (tests auth)
    3. Gets user's drive info (tests basic API access)
    4. Tests base folder accessibility (tests file path resolution)
    
    Use this for Phase 10 PoC initial validation after auth test passes.
    
    Returns:
        dict: Test result with status and details
        
    Example:
        result = test_onedrive_access()
        if result["success"]:
            print(f"OneDrive ready: {result['details']['drive_name']}")
        else:
            print(f"Failed: {result['error']}")
    """
    from app.services.graph_auth import (
        is_graph_fully_configured, 
        get_graph_config_status,
        test_graph_auth
    )
    
    result = {
        "test": "onedrive_access",
        "success": False,
        "error": None,
        "details": {}
    }
    
    # Step 1: Check full configuration
    if not is_graph_fully_configured():
        result["error"] = "OneDrive access not fully configured"
        result["details"]["config_status"] = get_graph_config_status()
        return result
    
    result["details"]["config_check"] = "passed"
    
    # Step 2: Test authentication first
    auth_result = test_graph_auth()
    if not auth_result["success"]:
        result["error"] = f"Authentication failed: {auth_result['error']}"
        result["details"]["auth_result"] = auth_result
        return result
    
    result["details"]["auth_check"] = "passed"
    
    # Step 3: Get user's drive info (read-only, safe)
    try:
        user_id = get_user_id()
        drive_endpoint = f"users/{user_id}/drive"
        
        drive_info = graph_get(drive_endpoint, timeout=30)
        
        result["details"]["drive_id"] = drive_info.get("id")
        result["details"]["drive_name"] = drive_info.get("name")
        result["details"]["drive_type"] = drive_info.get("driveType")
        result["details"]["quota_used"] = drive_info.get("quota", {}).get("used")
        result["details"]["quota_total"] = drive_info.get("quota", {}).get("total")
        result["details"]["drive_check"] = "passed"
        
    except GraphAPIError as e:
        result["error"] = f"Drive access failed: {e.message}"
        result["details"]["error_code"] = e.error_code
        result["details"]["status_code"] = e.status_code
        return result
    except ValueError as e:
        result["error"] = f"Configuration error: {str(e)}"
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        return result
    
    # Step 4: Check base folder exists (read-only, safe)
    try:
        base_folder = get_base_folder()
        # Use path-based access to check folder
        folder_endpoint = f"users/{user_id}/drive/root:/{base_folder}"
        
        folder_info = graph_get(folder_endpoint, timeout=30)
        
        if folder_info.get("folder"):
            result["details"]["base_folder_name"] = folder_info.get("name")
            result["details"]["base_folder_id"] = folder_info.get("id")
            result["details"]["base_folder_check"] = "passed"
        else:
            result["error"] = f"Path '{base_folder}' exists but is not a folder"
            result["details"]["base_folder_check"] = "failed"
            return result
            
    except GraphAPIError as e:
        if e.status_code == 404:
            result["error"] = f"Base folder '{base_folder}' not found on OneDrive"
            result["details"]["base_folder_check"] = "not_found"
            result["details"]["suggestion"] = f"Create folder '{base_folder}' on OneDrive first"
        else:
            result["error"] = f"Folder check failed: {e.message}"
            result["details"]["base_folder_check"] = "failed"
        return result
    except Exception as e:
        result["error"] = f"Folder check error: {str(e)}"
        return result
    
    # All checks passed
    result["success"] = True
    result["details"]["message"] = "OneDrive access fully verified - ready for Phase 10 PoC"
    
    return result


def test_graph_connectivity() -> dict:
    """
    Comprehensive connectivity test for Phase 10 PoC.
    
    Runs all safe tests in sequence:
    1. Configuration check
    2. Auth test
    3. OneDrive access test
    
    Returns:
        dict: Comprehensive test results
    """
    from app.services.graph_auth import (
        get_graph_readiness_report,
        test_graph_auth,
        is_graph_api_configured,
        is_graph_fully_configured
    )
    
    result = {
        "test": "graph_connectivity",
        "overall_success": False,
        "tests": {},
        "readiness_report": get_graph_readiness_report()
    }
    
    # Test 1: Auth
    auth_configured = is_graph_api_configured()
    if auth_configured:
        auth_result = test_graph_auth()
        result["tests"]["auth"] = auth_result
    else:
        result["tests"]["auth"] = {
            "success": False,
            "error": "Auth not configured",
            "skipped": True
        }
    
    # Test 2: OneDrive (only if auth works)
    fully_configured = is_graph_fully_configured()
    if fully_configured and result["tests"]["auth"].get("success"):
        onedrive_result = test_onedrive_access()
        result["tests"]["onedrive"] = onedrive_result
    else:
        result["tests"]["onedrive"] = {
            "success": False,
            "error": "Skipped - auth not working or not fully configured",
            "skipped": True
        }
    
    # Overall success
    result["overall_success"] = (
        result["tests"]["auth"].get("success", False) and
        result["tests"]["onedrive"].get("success", False)
    )
    
    if result["overall_success"]:
        result["message"] = "All connectivity tests passed - ready for Phase 10 PoC"
    else:
        failed_tests = [
            name for name, test in result["tests"].items() 
            if not test.get("success") and not test.get("skipped")
        ]
        if failed_tests:
            result["message"] = f"Tests failed: {', '.join(failed_tests)}"
        else:
            result["message"] = "Configuration incomplete - see readiness_report for details"
    
    return result
