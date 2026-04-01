"""
Graph API Health Monitor (Phase 9A.4)

This module provides health monitoring for Graph API calls:
    - Track success/failure rates
    - Monitor throttle events
    - Calculate response time averages
    - Circuit breaker pattern support

Usage:
    from app.services.graph_health_monitor import (
        record_success, record_failure, record_throttle,
        get_health_report, is_healthy
    )
    
    # Record an operation
    record_success(response_time_ms=150)
    
    # Get health report
    report = get_health_report()
    
    # Check health
    if is_healthy():
        # proceed

Author: Phase 9A.4 - Request Queue, Rate Limiting & Retry Engine
Date: 2026-02-28
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any

# Configure logging
logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class OperationRecord:
    """Record of a single operation."""
    timestamp: float
    success: bool
    response_time_ms: float
    operation: str = ""
    error_code: str = ""
    is_throttle: bool = False


class GraphHealthMonitor:
    """
    Monitors Graph API health metrics.
    
    Tracks:
        - Success/failure rates over sliding windows
        - Response time percentiles
        - Throttle events
        - Circuit breaker state
        
    Thresholds:
        - DEGRADED: < 95% success rate or > 5 throttles in 5 min
        - UNHEALTHY: < 80% success rate or > 20 throttles in 5 min
    """
    
    # Configuration
    WINDOW_SIZE_SECONDS = 300  # 5 minute sliding window
    MAX_RECORDS = 1000
    
    # Thresholds
    DEGRADED_SUCCESS_RATE = 0.95
    UNHEALTHY_SUCCESS_RATE = 0.80
    DEGRADED_THROTTLE_COUNT = 5
    UNHEALTHY_THROTTLE_COUNT = 20
    DEGRADED_AVG_RESPONSE_MS = 3000
    UNHEALTHY_AVG_RESPONSE_MS = 10000
    
    def __init__(self):
        self._records: deque = deque(maxlen=self.MAX_RECORDS)
        self._lock = threading.Lock()
        
        # Aggregated stats
        self._total_success = 0
        self._total_failure = 0
        self._total_throttle = 0
        
        # Response time tracking
        self._response_times: deque = deque(maxlen=100)
        
        # Circuit breaker state
        self._circuit_open = False
        self._circuit_open_until: float = 0
        self._consecutive_failures = 0
        
        # Last check timestamp
        self._last_health_check: float = 0
        self._cached_health: Optional[dict] = None
        
        logger.info("Graph health monitor initialized")
    
    def _prune_old_records(self):
        """Remove records outside the sliding window."""
        cutoff = time.time() - self.WINDOW_SIZE_SECONDS
        
        while self._records and self._records[0].timestamp < cutoff:
            self._records.popleft()
    
    def record_success(
        self,
        response_time_ms: float = 0,
        operation: str = ""
    ):
        """
        Record a successful operation.
        
        Args:
            response_time_ms: Response time in milliseconds
            operation: Optional operation name for breakdown
        """
        record = OperationRecord(
            timestamp=time.time(),
            success=True,
            response_time_ms=response_time_ms,
            operation=operation
        )
        
        with self._lock:
            self._records.append(record)
            self._total_success += 1
            self._consecutive_failures = 0
            
            if response_time_ms > 0:
                self._response_times.append(response_time_ms)
            
            self._cached_health = None  # Invalidate cache
    
    def record_failure(
        self,
        response_time_ms: float = 0,
        operation: str = "",
        error_code: str = ""
    ):
        """
        Record a failed operation.
        
        Args:
            response_time_ms: Response time in milliseconds
            operation: Optional operation name
            error_code: Error code from response
        """
        record = OperationRecord(
            timestamp=time.time(),
            success=False,
            response_time_ms=response_time_ms,
            operation=operation,
            error_code=error_code
        )
        
        with self._lock:
            self._records.append(record)
            self._total_failure += 1
            self._consecutive_failures += 1
            
            if response_time_ms > 0:
                self._response_times.append(response_time_ms)
            
            # Check circuit breaker
            if self._consecutive_failures >= 5:
                self._open_circuit(30)  # 30 second cooldown
            
            self._cached_health = None  # Invalidate cache
    
    def record_throttle(self, retry_after_seconds: int = 30):
        """
        Record a throttle (429) event.
        
        Args:
            retry_after_seconds: Retry-After value from response
        """
        record = OperationRecord(
            timestamp=time.time(),
            success=False,
            response_time_ms=0,
            error_code="429_throttle",
            is_throttle=True
        )
        
        with self._lock:
            self._records.append(record)
            self._total_throttle += 1
            self._cached_health = None
        
        logger.warning(
            f"⚠️ Throttle recorded (Retry-After: {retry_after_seconds}s). "
            f"Total throttles: {self._total_throttle}"
        )
    
    def _open_circuit(self, cooldown_seconds: int):
        """Open the circuit breaker."""
        if not self._circuit_open:
            self._circuit_open = True
            self._circuit_open_until = time.time() + cooldown_seconds
            logger.error(
                f"🔴 Circuit breaker OPEN - {self._consecutive_failures} consecutive failures. "
                f"Cooldown: {cooldown_seconds}s"
            )
    
    def _check_circuit(self) -> bool:
        """Check and update circuit breaker state."""
        if self._circuit_open:
            if time.time() >= self._circuit_open_until:
                self._circuit_open = False
                logger.info("🟢 Circuit breaker CLOSED - cooldown complete")
                return False
            return True
        return False
    
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        with self._lock:
            return self._check_circuit()
    
    def _get_window_stats(self) -> dict:
        """Calculate stats for the current sliding window."""
        self._prune_old_records()
        
        if not self._records:
            return {
                'success_count': 0,
                'failure_count': 0,
                'throttle_count': 0,
                'total_count': 0,
                'success_rate': 1.0,
                'avg_response_ms': 0
            }
        
        success_count = sum(1 for r in self._records if r.success)
        failure_count = sum(1 for r in self._records if not r.success)
        throttle_count = sum(1 for r in self._records if r.is_throttle)
        total_count = len(self._records)
        
        success_rate = success_count / total_count if total_count > 0 else 1.0
        
        response_times = [r.response_time_ms for r in self._records if r.response_time_ms > 0]
        avg_response = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'success_count': success_count,
            'failure_count': failure_count,
            'throttle_count': throttle_count,
            'total_count': total_count,
            'success_rate': round(success_rate, 4),
            'avg_response_ms': round(avg_response, 2)
        }
    
    def _calculate_percentiles(self) -> dict:
        """Calculate response time percentiles."""
        if not self._response_times:
            return {'p50': 0, 'p90': 0, 'p99': 0}
        
        sorted_times = sorted(self._response_times)
        n = len(sorted_times)
        
        p50 = sorted_times[int(n * 0.5)] if n > 0 else 0
        p90 = sorted_times[int(n * 0.9)] if n > 1 else p50
        p99 = sorted_times[int(n * 0.99)] if n > 1 else p90
        
        return {
            'p50': round(p50, 2),
            'p90': round(p90, 2),
            'p99': round(p99, 2)
        }
    
    def _determine_status(self, window_stats: dict) -> HealthStatus:
        """Determine health status based on metrics."""
        success_rate = window_stats['success_rate']
        throttle_count = window_stats['throttle_count']
        avg_response = window_stats['avg_response_ms']
        
        # Check for unhealthy conditions
        if success_rate < self.UNHEALTHY_SUCCESS_RATE:
            return HealthStatus.UNHEALTHY
        if throttle_count >= self.UNHEALTHY_THROTTLE_COUNT:
            return HealthStatus.UNHEALTHY
        if avg_response > self.UNHEALTHY_AVG_RESPONSE_MS:
            return HealthStatus.UNHEALTHY
        
        # Check for degraded conditions
        if success_rate < self.DEGRADED_SUCCESS_RATE:
            return HealthStatus.DEGRADED
        if throttle_count >= self.DEGRADED_THROTTLE_COUNT:
            return HealthStatus.DEGRADED
        if avg_response > self.DEGRADED_AVG_RESPONSE_MS:
            return HealthStatus.DEGRADED
        
        return HealthStatus.HEALTHY
    
    def get_health_report(self, force_refresh: bool = False) -> dict:
        """
        Get comprehensive health report.
        
        Args:
            force_refresh: Skip cache and recalculate
            
        Returns:
            dict with status, metrics, and details
        """
        with self._lock:
            # Return cached if recent (< 5 seconds old)
            if not force_refresh and self._cached_health:
                if time.time() - self._last_health_check < 5:
                    return self._cached_health
            
            window_stats = self._get_window_stats()
            percentiles = self._calculate_percentiles()
            status = self._determine_status(window_stats)
            circuit_open = self._check_circuit()
            
            report = {
                'status': status.value,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'windowSeconds': self.WINDOW_SIZE_SECONDS,
                
                # Current window metrics
                'successRate': window_stats['success_rate'],
                'successCount': window_stats['success_count'],
                'failureCount': window_stats['failure_count'],
                'throttleCount': window_stats['throttle_count'],
                'totalRequests': window_stats['total_count'],
                
                # Response times
                'avgResponseMs': window_stats['avg_response_ms'],
                'responseTimePercentiles': percentiles,
                
                # Circuit breaker
                'circuitBreaker': {
                    'isOpen': circuit_open,
                    'consecutiveFailures': self._consecutive_failures,
                    'reopensAt': datetime.fromtimestamp(
                        self._circuit_open_until
                    ).isoformat() + 'Z' if circuit_open else None
                },
                
                # Lifetime stats
                'lifetime': {
                    'totalSuccess': self._total_success,
                    'totalFailure': self._total_failure,
                    'totalThrottle': self._total_throttle,
                    'totalRequests': self._total_success + self._total_failure
                },
                
                # Thresholds for reference
                'thresholds': {
                    'degradedSuccessRate': self.DEGRADED_SUCCESS_RATE,
                    'unhealthySuccessRate': self.UNHEALTHY_SUCCESS_RATE,
                    'degradedThrottleCount': self.DEGRADED_THROTTLE_COUNT,
                    'unhealthyThrottleCount': self.UNHEALTHY_THROTTLE_COUNT
                }
            }
            
            # Cache result
            self._cached_health = report
            self._last_health_check = time.time()
            
            return report
    
    def is_healthy(self) -> bool:
        """
        Quick check if Graph API is healthy.
        
        Returns:
            True if status is HEALTHY, False otherwise
        """
        report = self.get_health_report()
        return report['status'] == HealthStatus.HEALTHY.value
    
    def reset(self):
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._records.clear()
            self._response_times.clear()
            self._total_success = 0
            self._total_failure = 0
            self._total_throttle = 0
            self._circuit_open = False
            self._circuit_open_until = 0
            self._consecutive_failures = 0
            self._cached_health = None
        
        logger.info("Health monitor reset")


# Global singleton instance
_health_monitor: Optional[GraphHealthMonitor] = None
_monitor_lock = threading.Lock()


def get_health_monitor() -> GraphHealthMonitor:
    """Get or create the global health monitor instance."""
    global _health_monitor
    
    with _monitor_lock:
        if _health_monitor is None:
            _health_monitor = GraphHealthMonitor()
        return _health_monitor


def record_success(response_time_ms: float = 0, operation: str = ""):
    """Record a successful operation."""
    get_health_monitor().record_success(response_time_ms, operation)


def record_failure(
    response_time_ms: float = 0,
    operation: str = "",
    error_code: str = ""
):
    """Record a failed operation."""
    get_health_monitor().record_failure(response_time_ms, operation, error_code)


def record_throttle(retry_after_seconds: int = 30):
    """Record a throttle event."""
    get_health_monitor().record_throttle(retry_after_seconds)


def get_health_report(force_refresh: bool = False) -> dict:
    """Get comprehensive health report."""
    return get_health_monitor().get_health_report(force_refresh)


def is_healthy() -> bool:
    """Quick health check."""
    return get_health_monitor().is_healthy()


def is_circuit_open() -> bool:
    """Check if circuit breaker is open."""
    return get_health_monitor().is_circuit_open()


def reset_health_monitor():
    """Reset health monitor (for testing)."""
    get_health_monitor().reset()
