#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Test configuration and fixtures for silvaengine_utility tests.
"""

import pytest
import logging
import sys
import os

# Add the package root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging for tests
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Disable JSON performance logging during tests unless specifically testing it
json_perf_logger = logging.getLogger('silvaengine_utility.json_performance')
json_perf_logger.setLevel(logging.CRITICAL)


@pytest.fixture
def sample_json_data():
    """Sample JSON data for testing."""
    return {
        "string_field": "test_value",
        "number_field": 42,
        "float_field": 3.14159,
        "boolean_field": True,
        "null_field": None,
        "array_field": [1, 2, 3, "test"],
        "nested_object": {
            "inner_string": "nested_value",
            "inner_number": 123
        }
    }


@pytest.fixture
def sample_datetime_strings():
    """Sample datetime strings for testing."""
    return [
        "2024-01-01T12:00:00Z",
        "2024-01-01T12:00:00.000Z",
        "2024-01-01T12:00:00+00:00",
        "2024-01-01T12:00:00.123456Z",
        "2024-01-01 12:00:00",
        "2024-01-01",
    ]


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    class MockLogger:
        def __init__(self):
            self.messages = {
                'debug': [],
                'info': [],
                'warning': [],
                'error': [],
                'critical': []
            }

        def debug(self, msg): self.messages['debug'].append(msg)
        def info(self, msg): self.messages['info'].append(msg)
        def warning(self, msg): self.messages['warning'].append(msg)
        def error(self, msg): self.messages['error'].append(msg)
        def critical(self, msg): self.messages['critical'].append(msg)

    return MockLogger()


# Optional dependencies
try:
    import orjson
    ORJSON_AVAILABLE = True
except ImportError:
    ORJSON_AVAILABLE = False

try:
    import pendulum
    PENDULUM_AVAILABLE = True
except ImportError:
    PENDULUM_AVAILABLE = False

# Pytest markers
pytest_plugins = []