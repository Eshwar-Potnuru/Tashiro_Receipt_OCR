"""
Conflict Resolution Handler (Phase 9A.3, refined Phase 11A-2)

This module provides automatic retry logic for ETag conflicts and
in-memory write serialization for concurrent access control.

Concurrency Model:
    1. ETag-based optimistic locking (handled by Graph API)
       - Each write includes If-Match header with current ETag
       - 412 Precondition Failed indicates another process modified the file
       
    2. In-memory write lock per file (handled by this module)
       - Prevents two threads/coroutines from writing to same file simultaneously
       - Uses threading Lock (does NOT work across processes or server instances)
       - Does NOT replace ETag checking - both are used together
       
    The combination ensures:
    - No two writes from this server instance overlap on the same file
    - If another server/user modifies the file, we detect and retry

SCOPE LIMITATIONS (Step 4 refinement):
    - In-memory locks are local to THIS process only
    - Multiple workers/processes: ETag is your only protection
    - Multiple server instances: ETag is your only protection
    - External users (SharePoint UI): ETag is your only protection
    
    For production multi-instance deployments, consider:
    - Redis-based distributed locking
    - Database-backed lease mechanism
    - Graph API's own locking features (if available)

FAILURE CLASSIFICATION (Phase 11A-2):
    - ETAG_CONFLICT: File modified by another process (412) - retryable
    - TRANSIENT: Temporary service issue (429, 502, 503, 504) - retryable
    - PERMANENT: Non-recoverable error (400, 403, 404, 500) - not retryable
    - TIMEOUT: Operation exceeded time limit - may be retryable
    - LOCK_TIMEOUT: Could not acquire write lock - may be retryable

Usage:
    from app.services.conflict_resolver import with_etag_retry, acquire_write_lock
    
    # Automatic retry wrapper
    result = with_etag_retry(
        lambda etag: append_row(file_id, "Sheet1", data, etag),
        file_id=file_id,
        get_etag_fn=lambda: get_file_metadata(file_id)['eTag']
    )
    
    # Manual lock management
    with acquire_write_lock(file_id):
        etag = get_file_metadata(file_id)['eTag']
        new_etag = append_row(file_id, "Sheet1", data, etag)

Author: Phase 9A.3 - Excel Write Operations with ETag Concurrency
        Phase 11A-2 - Conflict/Retry Completion
Date: 2026-02-28, refined 2026-03-21
"""

import logging
import threading
import time
from enum import Enum
from typing import Callable, Any, Optional, TypeVar, List
from functools import wraps
from contextlib import contextmanager

from app.services.excel_writer import ETagConflictError

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar('T')

# Global lock registry - maps file_id to Lock
_file_locks: dict = {}
_lock_registry_lock = threading.Lock()


# =============================================================================
# FAILURE CLASSIFICATION (Phase 11A-2)
# =============================================================================

class WriteFailureType(Enum):
    """
    Classification of write failure types for structured error handling.
    
    Phase 11A-2: Enables writers to make informed decisions about
    retry vs fail-fast vs user notification.
    """
    ETAG_CONFLICT = "etag_conflict"      # 412 - File modified, retry with fresh ETag
    TRANSIENT = "transient"               # 429, 502, 503, 504 - Temporary, may retry
    PERMANENT = "permanent"               # 400, 403, 404, 500 - Non-recoverable
    TIMEOUT = "timeout"                   # Operation timed out
    LOCK_TIMEOUT = "lock_timeout"         # Could not acquire write lock
    UNKNOWN = "unknown"                   # Unclassified error


# Status codes that indicate transient failures (retryable)
TRANSIENT_STATUS_CODES = {429, 502, 503, 504}

# Status codes that indicate permanent failures (not retryable)
PERMANENT_STATUS_CODES = {400, 401, 403, 404, 500}


def classify_write_error(error: Exception) -> WriteFailureType:
    """
    Classify an exception into a WriteFailureType for structured handling.
    
    Args:
        error: The exception to classify
        
    Returns:
        WriteFailureType indicating the nature of the failure
    """
    # ETag conflict (already specialized)
    if isinstance(error, ETagConflictError):
        return WriteFailureType.ETAG_CONFLICT
    
    # Lock timeout (must check before generic TimeoutError)
    if isinstance(error, LockTimeoutError):
        return WriteFailureType.LOCK_TIMEOUT
    
    # Timeout errors
    if isinstance(error, TimeoutError):
        return WriteFailureType.TIMEOUT
    
    # Check for GraphAPIError status codes
    try:
        from app.services.graph_client import GraphAPIError
        if isinstance(error, GraphAPIError):
            status = error.status_code
            if status == 412:
                return WriteFailureType.ETAG_CONFLICT
            if status in TRANSIENT_STATUS_CODES:
                return WriteFailureType.TRANSIENT
            if status in PERMANENT_STATUS_CODES:
                return WriteFailureType.PERMANENT
    except ImportError:
        pass
    
    # Check for RetryExhaustedError (transient failures exhausted retries)
    try:
        from app.services.retry_engine import RetryExhaustedError
        if isinstance(error, RetryExhaustedError):
            return WriteFailureType.TRANSIENT
    except ImportError:
        pass
    
    return WriteFailureType.UNKNOWN


def is_retryable_error(failure_type: WriteFailureType) -> bool:
    """
    Check if a failure type is potentially retryable.
    
    Args:
        failure_type: The WriteFailureType to check
        
    Returns:
        bool: True if the error might succeed on retry
    """
    return failure_type in {
        WriteFailureType.ETAG_CONFLICT,
        WriteFailureType.TRANSIENT,
        WriteFailureType.TIMEOUT,
        WriteFailureType.LOCK_TIMEOUT,
    }


class WriteConflictError(Exception):
    """
    Raised when a write operation fails permanently after all retries exhausted.
    
    This indicates persistent concurrent modification that couldn't be resolved
    through automatic retries.
    
    Attributes:
        file_id: OneDrive item ID
        worksheet_name: Name of the worksheet (if applicable)
        operation: Type of write operation
        attempts_count: Number of retry attempts made
        last_error: The final error that caused permanent failure
        failure_type: Classification of the failure (Phase 11A-2)
    """
    
    def __init__(
        self,
        file_id: str,
        operation: str,
        attempts_count: int,
        last_error: Exception,
        worksheet_name: str = None,
        failure_type: WriteFailureType = None
    ):
        self.file_id = file_id
        self.worksheet_name = worksheet_name
        self.operation = operation
        self.attempts_count = attempts_count
        self.last_error = last_error
        
        # Phase 11A-2: Classify the failure type for structured handling
        self.failure_type = failure_type or classify_write_error(last_error)
        
        # Step 4 refinement: Clearer error message with actionable guidance
        sheet_info = f" (worksheet: {worksheet_name})" if worksheet_name else ""
        failure_info = f" [type: {self.failure_type.value}]" if self.failure_type else ""
        self.message = (
            f"WRITE CONFLICT on file {file_id[:20]}...{sheet_info} during '{operation}'{failure_info}. "
            f"Failed after {attempts_count} attempts. "
            f"This typically means another user or process is actively modifying this file. "
            f"Last error: {str(last_error)}"
        )
        super().__init__(self.message)


class LockTimeoutError(Exception):
    """
    Raised when a write lock cannot be acquired within the timeout period.
    
    Phase 11A-2: Specialized exception for lock acquisition failures,
    separate from general TimeoutError.
    
    Attributes:
        file_id: OneDrive item ID
        timeout_seconds: The timeout that was exceeded
        message: Human-readable error message
    """
    
    def __init__(self, file_id: str, timeout_seconds: float):
        self.file_id = file_id
        self.timeout_seconds = timeout_seconds
        self.failure_type = WriteFailureType.LOCK_TIMEOUT
        self.message = (
            f"Could not acquire write lock for file {file_id[:20]}... "
            f"within {timeout_seconds}s. Another operation may be in progress."
        )
        super().__init__(self.message)


def _get_file_lock(file_id: str) -> threading.Lock:
    """
    Get or create a lock for a specific file.
    
    Thread-safe access to per-file locks.
    
    Args:
        file_id: OneDrive item ID
        
    Returns:
        Lock object for the file
    """
    with _lock_registry_lock:
        if file_id not in _file_locks:
            _file_locks[file_id] = threading.Lock()
        return _file_locks[file_id]


@contextmanager
def acquire_write_lock(file_id: str, timeout: float = 30.0):
    """
    Acquire an exclusive write lock for a file.
    
    This prevents two simultaneous writes to the same file from this server
    instance. Use this with a context manager:
    
    Args:
        file_id: OneDrive item ID
        timeout: Maximum time to wait for lock (seconds)
        
    Yields:
        None - use within context manager
        
    Raises:
        LockTimeoutError: If lock cannot be acquired within timeout (Phase 11A-2)
        
    Example:
        with acquire_write_lock(file_id):
            etag = get_file_metadata(file_id)['eTag']
            result = append_row(file_id, "Sheet1", data, etag)
    
    Note:
        This is an in-memory lock only. It does NOT prevent writes from
        other server instances or users. ETag checking handles cross-process
        conflicts.
    """
    lock = _get_file_lock(file_id)
    
    logger.debug(f"Acquiring write lock for file {file_id[:20]}...")
    
    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        # Phase 11A-2: Raise specialized exception for structured error handling
        raise LockTimeoutError(file_id, timeout)
    
    logger.debug(f"Write lock acquired for file {file_id[:20]}...")
    
    try:
        yield
    finally:
        lock.release()
        logger.debug(f"Write lock released for file {file_id[:20]}...")


def release_write_lock(file_id: str) -> bool:
    """
    Explicitly release a write lock for a file.
    
    Note: Normally use acquire_write_lock as a context manager instead.
    
    Args:
        file_id: OneDrive item ID
        
    Returns:
        bool: True if lock was released, False if no lock was held
    """
    lock = _get_file_lock(file_id)
    
    try:
        lock.release()
        logger.debug(f"Write lock explicitly released for file {file_id[:20]}...")
        return True
    except RuntimeError:
        # Lock was not held
        return False


def with_etag_retry(
    operation: Callable[[str], T],
    file_id: str,
    get_etag_fn: Callable[[], str],
    max_retries: int = 3,
    retry_delay: float = 0.5,
    worksheet_name: str = None,
    operation_name: str = "write"
) -> T:
    """
    Execute a write operation with automatic ETag conflict retry.
    
    If the operation raises ETagConflictError:
    1. Re-fetch the current ETag using get_etag_fn
    2. Retry the operation with the new ETag
    3. Repeat up to max_retries times
    
    The write lock is NOT automatically acquired - call this within
    acquire_write_lock context if single-server serialization is needed.
    
    Args:
        operation: Function that takes ETag and performs write, returns result
        file_id: OneDrive item ID (for error reporting)
        get_etag_fn: Function to fetch current ETag (usually get_file_metadata)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Delay between retries in seconds (default: 0.5)
        worksheet_name: Worksheet name for error reporting
        operation_name: Operation name for error reporting
        
    Returns:
        Return value of the operation function
        
    Raises:
        WriteConflictError: If all retries exhausted
        Other exceptions: If non-ETag errors occur
        
    Example:
        def write_op(etag):
            return append_row(file_id, "Sheet1", ["data"], etag)
        
        result = with_etag_retry(
            operation=write_op,
            file_id=file_id,
            get_etag_fn=lambda: get_file_metadata(file_id)['eTag']
        )
    """
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            # Fetch current ETag
            current_etag = get_etag_fn()
            
            if attempt > 0:
                logger.info(
                    f"Retry attempt {attempt}/{max_retries} for {operation_name} "
                    f"on {file_id[:20]}... with new ETag"
                )
            
            # Execute the operation
            result = operation(current_etag)
            
            if attempt > 0:
                logger.info(
                    f"Retry successful for {operation_name} on attempt {attempt + 1}"
                )
            
            return result
            
        except ETagConflictError as e:
            last_error = e
            
            if attempt < max_retries:
                logger.warning(
                    f"ETag conflict (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{operation_name} on {worksheet_name or 'file'}. Retrying..."
                )
                time.sleep(retry_delay)
            else:
                logger.error(
                    f"ETag conflict persists after {max_retries + 1} attempts: "
                    f"{operation_name} on {file_id[:20]}..."
                )
    
    # All retries exhausted - classify as ETag conflict since that's what we were retrying
    raise WriteConflictError(
        file_id=file_id,
        worksheet_name=worksheet_name,
        operation=operation_name,
        attempts_count=max_retries + 1,
        last_error=last_error,
        failure_type=WriteFailureType.ETAG_CONFLICT
    )


def with_etag_retry_decorator(
    file_id_param: str = "file_id",
    etag_param: str = "etag",
    worksheet_param: str = "worksheet_name",
    max_retries: int = 3
):
    """
    Decorator version of with_etag_retry for cleaner function decoration.
    
    Note: This requires the function to have specific parameter names.
    Requires get_file_metadata to be importable.
    
    Args:
        file_id_param: Name of the file_id parameter in decorated function
        etag_param: Name of the etag parameter in decorated function
        worksheet_param: Name of the worksheet parameter (optional)
        max_retries: Maximum retry attempts
        
    Example:
        @with_etag_retry_decorator(max_retries=3)
        def my_write_function(file_id, worksheet_name, data, etag):
            return append_row(file_id, worksheet_name, data, etag)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Import here to avoid circular imports
            from app.services.onedrive_file_manager import get_file_metadata
            
            # Extract file_id from kwargs or infer from args
            file_id = kwargs.get(file_id_param)
            worksheet_name = kwargs.get(worksheet_param)
            
            if file_id is None:
                # Try to get from positional args based on function signature
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                if file_id_param in params:
                    idx = params.index(file_id_param)
                    if idx < len(args):
                        file_id = args[idx]
            
            if file_id is None:
                raise ValueError(f"Could not determine {file_id_param} for retry wrapper")
            
            def get_etag():
                return get_file_metadata(file_id)['eTag']
            
            def operation(etag):
                new_kwargs = dict(kwargs)
                new_kwargs[etag_param] = etag
                return func(*args, **new_kwargs)
            
            return with_etag_retry(
                operation=operation,
                file_id=file_id,
                get_etag_fn=get_etag,
                max_retries=max_retries,
                worksheet_name=worksheet_name,
                operation_name=func.__name__
            )
        
        return wrapper
    return decorator


def safe_write(
    file_id: str,
    operation: Callable[[str], T],
    get_etag_fn: Callable[[], str],
    max_retries: int = 3,
    worksheet_name: str = None,
    operation_name: str = "write"
) -> T:
    """
    Execute a write operation with both write lock AND ETag retry.
    
    This is the RECOMMENDED way to perform writes (Step 4 refinement):
    - Use this for all production writes to OneDrive Excel files
    - Combines in-memory lock + ETag retry for best effort conflict resolution
    - Format① and Format② writers should use this exclusively
    
    Flow:
    1. Acquires exclusive in-memory lock for the file (same-process protection)
    2. Fetches current ETag
    3. Executes operation with If-Match header
    4. Retries on ETag conflict up to max_retries times (cross-process protection)
    5. Releases lock
    
    Args:
        file_id: OneDrive item ID (must be valid - no preflight validation)
        operation: Function that takes ETag and performs write
        get_etag_fn: Function to fetch current ETag
        max_retries: Maximum retry attempts (default: 3, with 0.5s delay between)
        worksheet_name: Worksheet name for logging
        operation_name: Operation name for logging
        
    Returns:
        Return value of the operation
        
    Raises:
        WriteConflictError: If all retries exhausted (persistent concurrent modification)
                           - failure_type=ETAG_CONFLICT when ETag mismatches persist
        LockTimeoutError: If write lock cannot be acquired within 30s
                         - failure_type=LOCK_TIMEOUT, includes file_id and timeout_seconds
        
    Example:
        from app.services.onedrive_file_manager import get_file_metadata
        from app.services.excel_writer import append_row
        
        new_etag = safe_write(
            file_id=file_id,
            operation=lambda etag: append_row(file_id, "Sheet1", data, etag),
            get_etag_fn=lambda: get_file_metadata(file_id)['eTag'],
            worksheet_name="Sheet1",
            operation_name="append_row"
        )
    """
    with acquire_write_lock(file_id):
        return with_etag_retry(
            operation=operation,
            file_id=file_id,
            get_etag_fn=get_etag_fn,
            max_retries=max_retries,
            worksheet_name=worksheet_name,
            operation_name=operation_name
        )


def clear_all_locks() -> int:
    """
    Clear all held file locks.
    
    Useful for testing or cleanup after errors.
    
    Returns:
        int: Number of locks cleared
    """
    global _file_locks
    
    with _lock_registry_lock:
        count = len(_file_locks)
        _file_locks = {}
        logger.info(f"Cleared {count} file locks")
        return count


def get_lock_status() -> dict:
    """
    Get status of all file locks.
    
    Returns:
        dict: Map of file_id to lock status (locked/unlocked)
    """
    with _lock_registry_lock:
        return {
            file_id: not lock.locked()  # True = available, False = locked
            for file_id, lock in _file_locks.items()
        }
