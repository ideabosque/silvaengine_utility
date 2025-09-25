#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Simple JSON Performance Monitor

Provides simple logging-based performance tracking for JSON operations.
"""

__author__ = "bibow"

import functools
import logging
import time
from typing import Callable

# Create logger for JSON performance
json_perf_logger = logging.getLogger("silvaengine_utility.json_performance")


class SimpleJSONPerformanceMonitor:
    """
    Simple performance monitor that logs JSON operation timing.

    Features:
    - Minimal overhead logging-based monitoring
    - Configurable log thresholds
    - Simple error reporting
    - No memory overhead for stats collection
    """

    def __init__(self, log_threshold: float = 0.01):
        """
        Initialize the simple performance monitor.

        Args:
            log_threshold: Only log operations that take longer than this threshold (in seconds)
        """
        self.log_threshold = log_threshold

    def monitor_json_operation(self, operation_name: str):
        """
        Simple decorator for logging JSON operation performance.

        Args:
            operation_name: Name of the operation (json_dumps, json_loads)

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    # Simple logging of performance - only log slow operations
                    if duration > self.log_threshold:
                        json_perf_logger.info(
                            f"{operation_name} completed in {duration:.4f}s"
                        )

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    json_perf_logger.warning(
                        f"{operation_name} failed after {duration:.4f}s: {str(e)}"
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
performance_monitor = SimpleJSONPerformanceMonitor()


# Convenience functions for backward compatibility
def set_performance_log_threshold(threshold: float):
    """Set the performance logging threshold."""
    performance_monitor.set_log_threshold(threshold)


def get_performance_log_threshold() -> float:
    """Get the current performance logging threshold."""
    return performance_monitor.get_log_threshold()
