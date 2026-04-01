"""
Request Queue with Rate Limiting (Phase 9A.4)

This module provides a request queue for Graph API calls with:
    - Priority-based queue (high, normal, low)
    - Concurrent request limiting (max 4 simultaneous)
    - Global pause on rate limiting (429) for Retry-After duration
    - Queue size limits with overflow protection

Usage:
    from app.services.request_queue import request_queue, enqueue, get_queue_stats
    
    # Enqueue a request
    result = enqueue(lambda: graph_get("me/drive"), priority='normal')
    
    # Check queue health
    stats = get_queue_stats()

Author: Phase 9A.4 - Request Queue, Rate Limiting & Retry Engine
Date: 2026-02-28
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from queue import PriorityQueue, Full, Empty
from typing import Callable, Any, Optional, Dict, List, TypeVar
from collections import deque

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar('T')


class Priority(Enum):
    """Request priority levels."""
    HIGH = 1
    NORMAL = 2
    LOW = 3
    
    @classmethod
    def from_string(cls, value: str) -> 'Priority':
        """Convert string to Priority enum."""
        return {
            'high': cls.HIGH,
            'normal': cls.NORMAL,
            'low': cls.LOW
        }.get(value.lower(), cls.NORMAL)


@dataclass(order=True)
class QueuedRequest:
    """
    A request waiting in the queue.
    
    Ordered by priority (lower number = higher priority),
    then by timestamp (FIFO within priority).
    """
    priority: int
    timestamp: float
    request_fn: Callable = field(compare=False)
    future: Future = field(compare=False)
    request_id: str = field(default='', compare=False)
    
    def __post_init__(self):
        if not self.request_id:
            self.request_id = f"req_{int(self.timestamp * 1000)}"


class QueueOverflowError(Exception):
    """Raised when the queue is full and cannot accept new requests."""
    
    def __init__(self, queue_size: int, max_size: int):
        self.queue_size = queue_size
        self.max_size = max_size
        super().__init__(
            f"Request queue overflow: {queue_size}/{max_size} items. "
            f"Try again later or use higher priority."
        )


class RequestQueue:
    """
    Priority-based request queue with rate limiting support.
    
    Features:
        - Max 4 concurrent requests
        - Priority queue (high > normal > low)
        - Global pause on 429 rate limiting
        - Queue size limit of 50 (configurable)
        
    Attributes:
        max_concurrent: Maximum simultaneous requests
        max_queue_size: Maximum queued requests
        is_paused: Whether processing is paused (rate limited)
        pause_until: Unix timestamp when pause ends
    """
    
    def __init__(
        self,
        max_concurrent: int = 4,
        max_queue_size: int = 50,
        low_priority_limit: int = None
    ):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        # Default: reserve 20% of queue for high/normal priority
        self.low_priority_limit = low_priority_limit if low_priority_limit is not None else max(1, int(max_queue_size * 0.2))
        
        # Queue state
        self._queue: PriorityQueue = PriorityQueue()
        self._queue_lock = threading.Lock()
        self._processing_count = 0
        self._processing_lock = threading.Lock()
        
        # Pause state for rate limiting
        self._is_paused = False
        self._pause_until: float = 0
        self._pause_lock = threading.Lock()
        
        # Stats tracking
        self._stats = {
            'total_enqueued': 0,
            'total_completed': 0,
            'total_failed': 0,
            'total_rejected': 0,
            'total_throttles': 0,
            'recent_wait_times': deque(maxlen=100),  # Last 100 wait times
            'recent_process_times': deque(maxlen=100)
        }
        self._stats_lock = threading.Lock()
        
        # Thread pool for async execution
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent,
            thread_name_prefix='graphqueue'
        )
        
        # Background worker thread
        self._worker_running = True
        self._worker_thread = threading.Thread(
            target=self._process_queue,
            daemon=True,
            name='graphqueue-worker'
        )
        self._worker_thread.start()
        
        logger.info(
            f"Request queue initialized: max_concurrent={max_concurrent}, "
            f"max_queue_size={max_queue_size}"
        )
    
    @property
    def is_paused(self) -> bool:
        """Check if queue is paused due to rate limiting."""
        with self._pause_lock:
            if self._is_paused and time.time() >= self._pause_until:
                self._is_paused = False
                logger.info("📗 Queue pause ended, resuming processing")
            return self._is_paused
    
    @property
    def pause_remaining_seconds(self) -> int:
        """Get remaining pause time in seconds."""
        with self._pause_lock:
            if not self._is_paused:
                return 0
            remaining = self._pause_until - time.time()
            return max(0, int(remaining))
    
    def pause_for_throttle(self, retry_after_seconds: int):
        """
        Pause queue processing due to rate limiting.
        
        Args:
            retry_after_seconds: Seconds to pause
        """
        with self._pause_lock:
            pause_until = time.time() + retry_after_seconds
            # Only extend pause if new time is later
            if pause_until > self._pause_until:
                self._is_paused = True
                self._pause_until = pause_until
                logger.warning(
                    f"⚠️ Queue paused for {retry_after_seconds}s due to rate limiting"
                )
        
        with self._stats_lock:
            self._stats['total_throttles'] += 1
    
    def _get_queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    def _get_low_priority_count(self) -> int:
        """Count low priority items in queue (approximate)."""
        # This is approximate since we can't iterate PriorityQueue safely
        return 0  # Simplified - full impl would track separately
    
    def enqueue(
        self,
        request_fn: Callable[[], T],
        priority: str = 'normal'
    ) -> Future:
        """
        Add a request to the queue.
        
        Args:
            request_fn: Function to execute (takes no arguments)
            priority: 'high', 'normal', or 'low'
            
        Returns:
            Future that will contain the result
            
        Raises:
            QueueOverflowError: If queue is full and request is rejected
        """
        priority_enum = Priority.from_string(priority)
        current_size = self._get_queue_size()
        
        # Check queue limits
        if current_size >= self.max_queue_size:
            # Reject low priority requests first
            if priority_enum == Priority.LOW:
                with self._stats_lock:
                    self._stats['total_rejected'] += 1
                raise QueueOverflowError(current_size, self.max_queue_size)
        
        # Check low priority limit
        if priority_enum == Priority.LOW:
            if current_size >= self.max_queue_size - self.low_priority_limit:
                with self._stats_lock:
                    self._stats['total_rejected'] += 1
                raise QueueOverflowError(current_size, self.max_queue_size)
        
        # Create future for result
        future = Future()
        
        # Create queued request
        queued = QueuedRequest(
            priority=priority_enum.value,
            timestamp=time.time(),
            request_fn=request_fn,
            future=future
        )
        
        # Add to queue
        with self._queue_lock:
            self._queue.put(queued)
        
        with self._stats_lock:
            self._stats['total_enqueued'] += 1
        
        logger.debug(f"Enqueued request {queued.request_id} with priority {priority}")
        
        return future
    
    def _process_queue(self):
        """Background worker that processes queued requests."""
        while self._worker_running:
            try:
                # Check if paused
                if self.is_paused:
                    time.sleep(1)
                    continue
                
                # Check if we can process more
                with self._processing_lock:
                    if self._processing_count >= self.max_concurrent:
                        time.sleep(0.1)
                        continue
                
                # Try to get next request
                try:
                    queued: QueuedRequest = self._queue.get(timeout=0.5)
                except Empty:
                    continue
                
                # Calculate wait time
                wait_time = (time.time() - queued.timestamp) * 1000
                with self._stats_lock:
                    self._stats['recent_wait_times'].append(wait_time)
                
                # Increment processing count
                with self._processing_lock:
                    self._processing_count += 1
                
                # Execute in thread pool
                self._executor.submit(self._execute_request, queued)
                
            except Exception as e:
                logger.error(f"Queue worker error: {e}")
                time.sleep(1)
    
    def _execute_request(self, queued: QueuedRequest):
        """Execute a single request and handle result."""
        start_time = time.time()
        
        try:
            result = queued.request_fn()
            queued.future.set_result(result)
            
            with self._stats_lock:
                self._stats['total_completed'] += 1
                process_time = (time.time() - start_time) * 1000
                self._stats['recent_process_times'].append(process_time)
            
            logger.debug(f"Request {queued.request_id} completed")
            
        except Exception as e:
            queued.future.set_exception(e)
            
            with self._stats_lock:
                self._stats['total_failed'] += 1
            
            # Check for throttling
            from app.services.graph_client import GraphAPIError
            if isinstance(e, GraphAPIError) and e.status_code == 429:
                # Get retry-after from error
                retry_after = 30  # Default
                if e.response_body and isinstance(e.response_body, dict):
                    inner_error = e.response_body.get('error', {})
                    retry_after = inner_error.get('retryAfterSeconds', 30)
                
                self.pause_for_throttle(retry_after)
            
            logger.warning(f"Request {queued.request_id} failed: {e}")
        
        finally:
            with self._processing_lock:
                self._processing_count -= 1
    
    def get_stats(self) -> dict:
        """
        Get queue statistics.
        
        Returns:
            dict with pending, processing, completed, failed, avgWaitMs, etc.
        """
        with self._stats_lock:
            wait_times = list(self._stats['recent_wait_times'])
            process_times = list(self._stats['recent_process_times'])
        
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
        avg_process = sum(process_times) / len(process_times) if process_times else 0
        
        return {
            'pending': self._get_queue_size(),
            'processing': self._processing_count,
            'completed': self._stats['total_completed'],
            'failed': self._stats['total_failed'],
            'rejected': self._stats['total_rejected'],
            'throttles': self._stats['total_throttles'],
            'avgWaitMs': round(avg_wait, 2),
            'avgProcessMs': round(avg_process, 2),
            'isPaused': self.is_paused,
            'pauseRemainingSeconds': self.pause_remaining_seconds,
            'maxConcurrent': self.max_concurrent,
            'maxQueueSize': self.max_queue_size
        }
    
    def shutdown(self, wait: bool = True):
        """
        Shutdown the queue.
        
        Args:
            wait: Whether to wait for pending requests to complete
        """
        logger.info("Shutting down request queue...")
        self._worker_running = False
        
        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        self._executor.shutdown(wait=wait)
        logger.info("Request queue shutdown complete")


# Global singleton instance
_request_queue: Optional[RequestQueue] = None
_queue_lock = threading.Lock()


def get_request_queue() -> RequestQueue:
    """Get or create the global request queue instance."""
    global _request_queue
    
    with _queue_lock:
        if _request_queue is None:
            _request_queue = RequestQueue()
        return _request_queue


def enqueue(
    request_fn: Callable[[], T],
    priority: str = 'normal',
    wait: bool = True,
    timeout: float = None
) -> T:
    """
    Enqueue a request and optionally wait for result.
    
    Args:
        request_fn: Function to execute
        priority: 'high', 'normal', or 'low'
        wait: Whether to wait for result (default: True)
        timeout: Timeout in seconds if waiting
        
    Returns:
        Result of request_fn if wait=True, else Future
        
    Raises:
        QueueOverflowError: If queue full and low priority
        TimeoutError: If wait times out
        Exception: Any exception from request_fn
    """
    queue = get_request_queue()
    future = queue.enqueue(request_fn, priority)
    
    if not wait:
        return future
    
    return future.result(timeout=timeout)


def get_queue_stats() -> dict:
    """Get queue statistics."""
    return get_request_queue().get_stats()


def pause_queue(seconds: int):
    """Manually pause the queue."""
    get_request_queue().pause_for_throttle(seconds)


def is_queue_healthy() -> bool:
    """Check if queue is healthy (not paused, not overloaded)."""
    queue = get_request_queue()
    stats = queue.get_stats()
    
    # Unhealthy if paused or > 80% capacity
    if stats['isPaused']:
        return False
    if stats['pending'] > queue.max_queue_size * 0.8:
        return False
    
    return True
