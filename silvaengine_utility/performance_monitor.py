#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Generic Performance Monitor

Provides simple logging-based performance tracking for any operations.
"""

__author__ = "bibow"

import functools
import logging
from typing import Callable

import pendulum

# Create logger for performance monitoring
perf_logger = logging.getLogger("silvaengine_utility.performance")


class SimplePerformanceMonitor:
    """
    Simple performance monitor that logs operation timing.

    Features:
    - Minimal overhead logging-based monitoring
    - Configurable log thresholds
    - Simple error reporting
    - No memory overhead for stats collection
    """

    def __init__(self, log_threshold: float = 0.1):
        """
        Initialize the simple performance monitor.

        Args:
            log_threshold: Only log operations that take longer than this threshold (in seconds)
        """
        self.log_threshold = log_threshold  # Store in seconds for backward compatibility

    def monitor_operation(
        self, log_threshold: float = None, operation_name: str = None
    ):
        """
        Simple decorator for logging operation performance.

        Args:
            log_threshold: Override threshold for this operation (in seconds)
            operation_name: Optional name to prefix the operation log messages

        Returns:
            Decorator function that wraps the target operation with performance monitoring
        """
        _log_threshold = self.log_threshold
        if log_threshold is not None:
            _log_threshold = min(log_threshold, self.log_threshold)

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = pendulum.now("UTC")
                op_name = (
                    f"{operation_name}: {func.__name__}"
                    if operation_name is not None
                    else func.__name__
                )
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (pendulum.now("UTC") - start_time).total_seconds() * 1000

                    # Simple logging of performance - only log slow operations
                    # Convert threshold from seconds to milliseconds for comparison
                    if duration_ms > (_log_threshold * 1000):
                        perf_logger.info(f"{op_name} completed in {duration_ms:.2f}ms")

                    return result

                except Exception as e:
                    duration_ms = (pendulum.now("UTC") - start_time).total_seconds() * 1000
                    perf_logger.warning(
                        f"{op_name} failed after {duration_ms:.2f}ms: {str(e)}"
                    )
                    raise

            return wrapper

        return decorator

    def set_log_threshold(self, threshold: float):
        """Set the minimum duration threshold for logging operations."""
        self.log_threshold = threshold

    def get_log_threshold(self) -> float:
        """Get the current log threshold."""
        return self.log_threshold


# Global performance monitor instance
performance_monitor = SimplePerformanceMonitor()


# Convenience functions for backward compatibility
def set_performance_log_threshold(threshold: float):
    """Set the performance logging threshold."""
    performance_monitor.set_log_threshold(threshold)


def get_performance_log_threshold() -> float:
    """Get the current performance logging threshold."""
    return performance_monitor.get_log_threshold()
