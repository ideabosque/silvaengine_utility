#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Tests for the simple JSON performance monitor.
"""

import pytest
import time
import logging
from unittest.mock import Mock, patch
from io import StringIO

from silvaengine_utility.performance_monitor import (
    SimpleJSONPerformanceMonitor,
    performance_monitor,
    set_performance_log_threshold,
    get_performance_log_threshold,
    json_perf_logger
)


class TestSimpleJSONPerformanceMonitor:
    """Test the SimpleJSONPerformanceMonitor class."""

    def test_monitor_initialization(self):
        """Test monitor initialization with default threshold."""
        monitor = SimpleJSONPerformanceMonitor()
        assert monitor.log_threshold == 0.01  # Default threshold

    def test_monitor_initialization_custom_threshold(self):
        """Test monitor initialization with custom threshold."""
        custom_threshold = 0.5
        monitor = SimpleJSONPerformanceMonitor(log_threshold=custom_threshold)
        assert monitor.log_threshold == custom_threshold

    def test_set_and_get_log_threshold(self):
        """Test setting and getting log threshold."""
        monitor = SimpleJSONPerformanceMonitor()

        # Test default
        assert monitor.get_log_threshold() == 0.01

        # Test setting new threshold
        monitor.set_log_threshold(0.2)
        assert monitor.get_log_threshold() == 0.2

        # Test setting zero threshold
        monitor.set_log_threshold(0.0)
        assert monitor.get_log_threshold() == 0.0

    def test_decorator_basic_functionality(self):
        """Test that the decorator works without breaking the function."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=999)  # High threshold to prevent logging

        @monitor.monitor_json_operation("test_operation")
        def test_function(value):
            return value * 2

        result = test_function(5)
        assert result == 10

    def test_decorator_preserves_function_metadata(self):
        """Test that the decorator preserves function metadata."""
        monitor = SimpleJSONPerformanceMonitor()

        @monitor.monitor_json_operation("test_operation")
        def test_function():
            """Test function docstring."""
            return "test"

        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test function docstring."

    def test_performance_logging_slow_operation(self, caplog):
        """Test that slow operations are logged."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.01)  # 10ms threshold

        @monitor.monitor_json_operation("slow_operation")
        def slow_function():
            time.sleep(0.02)  # Sleep for 20ms
            return "completed"

        with caplog.at_level(logging.INFO, logger='silvaengine_utility.json_performance'):
            result = slow_function()

        assert result == "completed"
        # Check if performance was logged
        log_messages = [record.message for record in caplog.records]
        assert any("slow_operation completed" in msg for msg in log_messages)

    def test_performance_logging_fast_operation(self, caplog):
        """Test that fast operations are not logged."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=1.0)  # 1 second threshold

        @monitor.monitor_json_operation("fast_operation")
        def fast_function():
            return "completed quickly"

        with caplog.at_level(logging.INFO, logger='silvaengine_utility.json_performance'):
            result = fast_function()

        assert result == "completed quickly"
        # Should not log fast operations
        log_messages = [record.message for record in caplog.records]
        assert not any("fast_operation completed" in msg for msg in log_messages)

    def test_error_logging(self, caplog):
        """Test that errors are logged with performance timing."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.001)

        @monitor.monitor_json_operation("error_operation")
        def error_function():
            raise ValueError("Test error")

        with caplog.at_level(logging.WARNING, logger='silvaengine_utility.json_performance'):
            with pytest.raises(ValueError, match="Test error"):
                error_function()

        # Check that error was logged with timing
        log_messages = [record.message for record in caplog.records]
        error_logged = any("error_operation failed" in msg and "Test error" in msg for msg in log_messages)
        assert error_logged

    def test_exception_propagation(self):
        """Test that exceptions are properly propagated."""
        monitor = SimpleJSONPerformanceMonitor()

        @monitor.monitor_json_operation("exception_operation")
        def exception_function():
            raise RuntimeError("Custom error")

        # Exception should be propagated
        with pytest.raises(RuntimeError, match="Custom error"):
            exception_function()

    def test_multiple_operations_different_names(self, caplog):
        """Test monitoring multiple operations with different names."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.001)

        @monitor.monitor_json_operation("operation_a")
        def operation_a():
            time.sleep(0.01)
            return "A"

        @monitor.monitor_json_operation("operation_b")
        def operation_b():
            time.sleep(0.01)
            return "B"

        with caplog.at_level(logging.INFO, logger='silvaengine_utility.json_performance'):
            result_a = operation_a()
            result_b = operation_b()

        assert result_a == "A"
        assert result_b == "B"

        # Both operations should be logged
        log_messages = [record.message for record in caplog.records]
        assert any("operation_a completed" in msg for msg in log_messages)
        assert any("operation_b completed" in msg for msg in log_messages)


class TestGlobalPerformanceMonitor:
    """Test the global performance_monitor instance."""

    def test_global_monitor_exists(self):
        """Test that global monitor instance exists."""
        assert performance_monitor is not None
        assert isinstance(performance_monitor, SimpleJSONPerformanceMonitor)

    def test_global_convenience_functions(self):
        """Test global convenience functions."""
        original_threshold = get_performance_log_threshold()

        # Test setting new threshold
        set_performance_log_threshold(0.5)
        assert get_performance_log_threshold() == 0.5

        # Test setting back to original
        set_performance_log_threshold(original_threshold)
        assert get_performance_log_threshold() == original_threshold

    def test_global_monitor_decorator_usage(self):
        """Test using the global monitor decorator."""
        @performance_monitor.monitor_json_operation("global_test")
        def global_test_function():
            return "global result"

        result = global_test_function()
        assert result == "global result"


class TestLoggingIntegration:
    """Test logging integration and configuration."""

    def test_logger_configuration(self):
        """Test that the JSON performance logger is properly configured."""
        assert json_perf_logger.name == "silvaengine_utility.json_performance"

    def test_logging_with_different_levels(self):
        """Test logging behavior with different log levels."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.001)

        @monitor.monitor_json_operation("level_test")
        def test_function():
            time.sleep(0.01)
            return "test"

        # Test with INFO level
        with patch.object(json_perf_logger, 'info') as mock_info:
            test_function()
            mock_info.assert_called()

        # Test error logging
        @monitor.monitor_json_operation("error_level_test")
        def error_function():
            raise Exception("Test exception")

        with patch.object(json_perf_logger, 'warning') as mock_warning:
            with pytest.raises(Exception):
                error_function()
            mock_warning.assert_called()

    def test_log_message_format(self, caplog):
        """Test the format of logged messages."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.001)

        @monitor.monitor_json_operation("format_test")
        def test_function():
            time.sleep(0.01)
            return "test"

        with caplog.at_level(logging.INFO, logger='silvaengine_utility.json_performance'):
            test_function()

        # Check message format
        assert len(caplog.records) > 0
        message = caplog.records[0].message

        # Should contain operation name and time
        assert "format_test completed in" in message
        assert "s" in message  # Time unit

    def test_error_log_message_format(self, caplog):
        """Test the format of error log messages."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.001)

        @monitor.monitor_json_operation("error_format_test")
        def error_function():
            raise ValueError("Specific error message")

        with caplog.at_level(logging.WARNING, logger='silvaengine_utility.json_performance'):
            with pytest.raises(ValueError):
                error_function()

        # Check error message format
        assert len(caplog.records) > 0
        message = caplog.records[0].message

        # Should contain operation name, time, and error message
        assert "error_format_test failed after" in message
        assert "Specific error message" in message


class TestPerformanceMonitorEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_threshold(self, caplog):
        """Test behavior with zero threshold (log everything)."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.0)

        @monitor.monitor_json_operation("zero_threshold_test")
        def fast_function():
            return "fast"

        with caplog.at_level(logging.INFO, logger='silvaengine_utility.json_performance'):
            result = fast_function()

        assert result == "fast"
        # Should log even very fast operations
        log_messages = [record.message for record in caplog.records]
        assert any("zero_threshold_test completed" in msg for msg in log_messages)

    def test_very_high_threshold(self, caplog):
        """Test behavior with very high threshold (log nothing)."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=999.0)

        @monitor.monitor_json_operation("high_threshold_test")
        def slow_function():
            time.sleep(0.01)  # 10ms - still much less than 999s
            return "slow"

        with caplog.at_level(logging.INFO, logger='silvaengine_utility.json_performance'):
            result = slow_function()

        assert result == "slow"
        # Should not log due to high threshold
        log_messages = [record.message for record in caplog.records]
        assert not any("high_threshold_test completed" in msg for msg in log_messages)

    def test_negative_threshold(self):
        """Test behavior with negative threshold."""
        # Should still work (negative threshold means log everything)
        monitor = SimpleJSONPerformanceMonitor(log_threshold=-1.0)
        assert monitor.log_threshold == -1.0

        @monitor.monitor_json_operation("negative_threshold_test")
        def test_function():
            return "test"

        result = test_function()
        assert result == "test"

    def test_concurrent_operations(self):
        """Test that concurrent operations don't interfere."""
        import threading
        import queue

        monitor = SimpleJSONPerformanceMonitor(log_threshold=0.001)
        results = queue.Queue()

        @monitor.monitor_json_operation("concurrent_test")
        def concurrent_function(thread_id):
            time.sleep(0.01)
            return f"thread_{thread_id}"

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(
                target=lambda tid=i: results.put(concurrent_function(tid))
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Collect results
        collected_results = []
        while not results.empty():
            collected_results.append(results.get())

        # Should have results from all threads
        assert len(collected_results) == 5
        for i in range(5):
            assert f"thread_{i}" in collected_results

    def test_decorator_with_args_and_kwargs(self):
        """Test decorator with functions that have args and kwargs."""
        monitor = SimpleJSONPerformanceMonitor(log_threshold=999)  # High threshold

        @monitor.monitor_json_operation("args_kwargs_test")
        def complex_function(a, b, c=None, *args, **kwargs):
            return {
                'a': a,
                'b': b,
                'c': c,
                'args': args,
                'kwargs': kwargs
            }

        result = complex_function(1, 2, c=3, 4, 5, x=10, y=20)

        expected = {
            'a': 1,
            'b': 2,
            'c': 3,
            'args': (4, 5),
            'kwargs': {'x': 10, 'y': 20}
        }

        assert result == expected