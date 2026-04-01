"""
Retry Engine with Exponential Backoff (Phase 9A.4)

This module provides retry logic with exponential backoff for Graph API calls.
It handles transient failures including rate limiting (429), service unavailable (503),
network errors, and ETag conflicts.

Features:
    - Exponential backoff with jitter to prevent thundering herd
    - Configurable retry conditions by status code or exception type
    - Callback support for retry monitoring
    - Detailed tracking of all retry attempts

Usage:
    from app.services.retry_engine import with_retry, RetryExhaustedError
    
    result = with_retry(
        lambda: graph_get("me/drive"),
        max_retries=3,
        retry_on=[429, 503]
    )

Author: Phase 9A.4 - Request Queue, Rate Limiting & Retry Engine
Date: 2026-02-28
"""

import logging
import random
import time
from typing import Callable, Any, List, Optional, Union, TypeVar
from functools import wraps

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar('T')

# Default retry conditions
DEFAULT_RETRY_STATUS_CODES = [429, 503, 502, 504]
DEFAULT_RETRY_ERROR_CODES = ['timeout', 'connection_error', 'network_error']


class RetryExhaustedError(Exception):
    """
    Raised when all retry attempts have been exhausted.
    
    Attributes:
        attempts: Number of attempts made
        last_error: The final error that caused failure
        total_time_ms: Total time spent on all attempts
        operation: Name/description of the operation
        attempt_details: List of dicts with details for each attempt
    """
    
    def __init__(
        self,
        operation: str,
        attempts: int,
        last_error: Exception,
        total_time_ms: float,
        attempt_details: List[dict] = None
    ):
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error
        self.total_time_ms = total_time_ms
        self.attempt_details = attempt_details or []
        
        self.message = (
            f"Retry exhausted for '{operation}' after {attempts} attempts. "
            f"Total time: {total_time_ms:.0f}ms. "
            f"Last error: {str(last_error)}"
        )
        super().__init__(self.message)


class ThrottleInfo:
    """
    Container for rate limit throttle information.
    
    Attributes:
        retry_after_seconds: Number of seconds to wait
        request_id: Graph API request ID
        timestamp: When throttle was detected
    """
    
    def __init__(self, retry_after_seconds: int, request_id: str = None):
        self.retry_after_seconds = retry_after_seconds
        self.request_id = request_id
        self.timestamp = time.time()


def calculate_backoff(
    attempt: int,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
    add_jitter: bool = True
) -> int:
    """
    Calculate backoff delay using exponential formula with optional jitter.
    
    Formula: min(base_delay * 2^attempt + jitter, max_delay)
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_delay_ms: Base delay in milliseconds
        max_delay_ms: Maximum delay cap in milliseconds
        add_jitter: Whether to add random jitter (0-500ms)
        
    Returns:
        Delay in milliseconds
    """
    # Exponential backoff
    delay = base_delay_ms * (2 ** attempt)
    
    # Add jitter to prevent thundering herd
    if add_jitter:
        jitter = random.randint(0, 500)
        delay += jitter
    
    # Cap at max delay
    return min(delay, max_delay_ms)


def should_retry(
    error: Exception,
    retry_on_status_codes: List[int] = None,
    retry_on_error_codes: List[str] = None
) -> tuple:
    """
    Determine if an error should trigger a retry.
    
    Args:
        error: The exception that occurred
        retry_on_status_codes: HTTP status codes to retry on
        retry_on_error_codes: Error code strings to retry on
        
    Returns:
        Tuple of (should_retry: bool, retry_after_seconds: int or None)
    """
    retry_on_status_codes = retry_on_status_codes or DEFAULT_RETRY_STATUS_CODES
    retry_on_error_codes = retry_on_error_codes or DEFAULT_RETRY_ERROR_CODES
    
    retry_after = None
    
    # Import here to avoid circular imports
    from app.services.graph_client import GraphAPIError
    
    # Check for GraphAPIError with status code
    if isinstance(error, GraphAPIError):
        status_code = error.status_code
        error_code = error.error_code
        
        # Check for rate limiting (429) - extract Retry-After
        if status_code == 429:
            # Try to get Retry-After from response body
            if error.response_body and isinstance(error.response_body, dict):
                inner_error = error.response_body.get('error', {})
                retry_after = inner_error.get('retryAfterSeconds')
            
            # Default to 30 seconds if not specified
            if retry_after is None:
                retry_after = 30
            
            logger.warning(f"⚠️ Graph API throttled. Retry-After: {retry_after}s")
            return (True, retry_after)
        
        # Check status code match
        if status_code in retry_on_status_codes:
            return (True, None)
        
        # Check error code match
        if error_code and error_code in retry_on_error_codes:
            return (True, None)
    
    # Check for ETagConflictError
    try:
        from app.services.excel_writer import ETagConflictError
        if isinstance(error, ETagConflictError):
            return (True, None)
    except ImportError:
        pass
    
    # Check for network-related errors
    import requests
    if isinstance(error, (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        ConnectionError,
        TimeoutError
    )):
        return (True, None)
    
    return (False, None)


def with_retry(
    fn: Callable[[], T],
    max_retries: int = 4,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
    retry_on_status_codes: List[int] = None,
    retry_on_error_codes: List[str] = None,
    on_retry: Callable[[int, Exception, int], None] = None,
    operation_name: str = None
) -> T:
    """
    Execute a function with automatic retry on failure.
    
    Uses exponential backoff with jitter. Respects Retry-After headers
    from rate limiting responses.
    
    Args:
        fn: Function to execute (should take no arguments)
        max_retries: Maximum number of retry attempts (default: 4)
        base_delay_ms: Base delay for backoff in ms (default: 1000)
        max_delay_ms: Maximum delay cap in ms (default: 30000)
        retry_on_status_codes: HTTP status codes to retry on
        retry_on_error_codes: Error codes to retry on
        on_retry: Optional callback(attempt, error, delay_ms) called before each retry
        operation_name: Description for logging/error reporting
        
    Returns:
        Return value of fn() on success
        
    Raises:
        RetryExhaustedError: If all retries exhausted
        Exception: Re-raises non-retryable errors immediately
        
    Example:
        result = with_retry(
            lambda: graph_get("me/drive"),
            max_retries=3,
            operation_name="get_drive_info"
        )
    """
    operation = operation_name or fn.__name__ if hasattr(fn, '__name__') else 'unknown'
    start_time = time.time()
    attempt_details = []
    last_error = None
    
    for attempt in range(max_retries + 1):
        attempt_start = time.time()
        
        try:
            result = fn()
            
            # Log success after retries
            if attempt > 0:
                total_time = (time.time() - start_time) * 1000
                logger.info(
                    f"Operation '{operation}' succeeded on attempt {attempt + 1} "
                    f"(total time: {total_time:.0f}ms)"
                )
            
            return result
            
        except Exception as e:
            last_error = e
            attempt_duration = (time.time() - attempt_start) * 1000
            
            # Record attempt details
            attempt_details.append({
                'attempt': attempt + 1,
                'error': str(e),
                'error_type': type(e).__name__,
                'duration_ms': attempt_duration
            })
            
            # Check if we should retry
            should_retry_flag, retry_after = should_retry(
                e, retry_on_status_codes, retry_on_error_codes
            )
            
            if not should_retry_flag:
                logger.debug(f"Error not retryable: {type(e).__name__}")
                raise
            
            if attempt >= max_retries:
                # No more retries
                break
            
            # Calculate delay
            if retry_after:
                delay_ms = retry_after * 1000
            else:
                delay_ms = calculate_backoff(attempt, base_delay_ms, max_delay_ms)
            
            logger.warning(
                f"Retry {attempt + 1}/{max_retries} for '{operation}': "
                f"{type(e).__name__} - waiting {delay_ms}ms"
            )
            
            # Call retry callback if provided
            if on_retry:
                try:
                    on_retry(attempt + 1, e, delay_ms)
                except Exception:
                    pass  # Don't fail on callback error
            
            # Wait before retry
            time.sleep(delay_ms / 1000)
    
    # All retries exhausted
    total_time = (time.time() - start_time) * 1000
    
    raise RetryExhaustedError(
        operation=operation,
        attempts=max_retries + 1,
        last_error=last_error,
        total_time_ms=total_time,
        attempt_details=attempt_details
    )


def retry_decorator(
    max_retries: int = 4,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
    retry_on_status_codes: List[int] = None,
    retry_on_error_codes: List[str] = None
):
    """
    Decorator version of with_retry for cleaner function decoration.
    
    Args:
        max_retries: Maximum retry attempts
        base_delay_ms: Base backoff delay
        max_delay_ms: Maximum backoff delay
        retry_on_status_codes: Status codes to retry on
        retry_on_error_codes: Error codes to retry on
        
    Example:
        @retry_decorator(max_retries=3)
        def my_graph_operation():
            return graph_get("me/drive")
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return with_retry(
                fn=lambda: fn(*args, **kwargs),
                max_retries=max_retries,
                base_delay_ms=base_delay_ms,
                max_delay_ms=max_delay_ms,
                retry_on_status_codes=retry_on_status_codes,
                retry_on_error_codes=retry_on_error_codes,
                operation_name=fn.__name__
            )
        return wrapper
    return decorator


def get_retry_delay_info(attempt: int, base_delay_ms: int = 1000, max_delay_ms: int = 30000) -> dict:
    """
    Get information about retry delay for a given attempt.
    
    Useful for understanding backoff behavior.
    
    Args:
        attempt: Attempt number (0-indexed)
        base_delay_ms: Base delay
        max_delay_ms: Maximum delay
        
    Returns:
        dict with delay calculation details
    """
    exponential = base_delay_ms * (2 ** attempt)
    delay_with_jitter = calculate_backoff(attempt, base_delay_ms, max_delay_ms, add_jitter=True)
    
    return {
        'attempt': attempt,
        'exponential_delay_ms': exponential,
        'with_jitter_ms': delay_with_jitter,
        'capped': delay_with_jitter >= max_delay_ms,
        'max_delay_ms': max_delay_ms
    }
