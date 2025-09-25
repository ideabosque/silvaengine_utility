#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Comprehensive tests for JSON handler functionality.
"""

import json
import pytest
from decimal import Decimal
from datetime import datetime, date
from typing import Any

from silvaengine_utility.json_handler import (
    HighPerformanceJSONHandler,
    JSONDecoder,
    JSONHandler
)

# Check for optional dependencies
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

try:
    import pendulum
    HAS_PENDULUM = True
except ImportError:
    HAS_PENDULUM = False


class TestJSONDecoder:
    """Test the custom JSONDecoder class."""

    def test_json_decoder_decimal_parsing(self):
        """Test that JSONDecoder properly parses numbers as Decimal."""
        decoder = JSONDecoder()
        test_json = '{"price": 123.45, "quantity": 10, "rate": 0.1}'

        result = json.loads(test_json, cls=JSONDecoder)

        assert isinstance(result["price"], Decimal)
        assert result["price"] == Decimal("123.45")
        assert isinstance(result["quantity"], Decimal)
        assert result["quantity"] == Decimal("10")
        assert isinstance(result["rate"], Decimal)
        assert result["rate"] == Decimal("0.1")

    def test_json_decoder_initialization(self):
        """Test JSONDecoder initialization with custom parameters."""
        # Test with explicit parameters
        decoder = JSONDecoder(parse_float=float, parse_int=int)
        test_json = '{"price": 123.45, "quantity": 10}'

        result = json.loads(test_json, cls=decoder)

        # Should use the overridden parameters, not defaults
        assert isinstance(result["price"], float)
        assert isinstance(result["quantity"], int)

    def test_json_decoder_default_behavior(self):
        """Test JSONDecoder uses Decimal by default."""
        decoder = JSONDecoder()
        test_json = '{"value": 42.0}'

        result = json.loads(test_json, cls=decoder)

        assert isinstance(result["value"], Decimal)
        assert result["value"] == Decimal("42.0")


class TestHighPerformanceJSONHandler:
    """Test the HighPerformanceJSONHandler class."""

    def test_library_info(self):
        """Test library information reporting."""
        info = HighPerformanceJSONHandler.get_library_info()

        assert "library" in info
        assert "high_performance" in info
        assert "version" in info

        if HAS_ORJSON:
            assert info["library"] == "orjson"
            assert info["high_performance"] is True
        else:
            assert info["library"] == "json"
            assert info["high_performance"] is False

    def test_basic_serialization(self, sample_json_data):
        """Test basic JSON serialization."""
        result = HighPerformanceJSONHandler.dumps(sample_json_data)

        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["string_field"] == "test_value"
        assert parsed["number_field"] == 42

    def test_compact_serialization(self, sample_json_data):
        """Test compact JSON serialization."""
        compact = HighPerformanceJSONHandler.dumps(sample_json_data, compact=True)
        regular = HighPerformanceJSONHandler.dumps(sample_json_data, compact=False)

        # Compact should be shorter (no indentation)
        assert len(compact) < len(regular)

        # Both should parse to the same data
        assert json.loads(compact) == json.loads(regular)

    def test_decimal_serialization(self):
        """Test serialization of Decimal objects."""
        data = {
            "price": Decimal("123.45"),
            "tax": Decimal("0.08"),
            "total": Decimal("133.3260")
        }

        result = HighPerformanceJSONHandler.dumps(data)
        parsed = json.loads(result)

        # Decimals should be serialized as floats
        assert isinstance(parsed["price"], float)
        assert parsed["price"] == 123.45

    def test_datetime_serialization(self):
        """Test serialization of datetime objects."""
        test_datetime = datetime(2024, 1, 1, 12, 0, 0)
        test_date = date(2024, 1, 1)

        data = {
            "timestamp": test_datetime,
            "date": test_date
        }

        result = HighPerformanceJSONHandler.dumps(data)
        parsed = json.loads(result)

        assert parsed["timestamp"] == "2024-01-01T12:00:00"
        assert parsed["date"] == "2024-01-01"

    def test_parser_number_true(self):
        """Test loads with parser_number=True (Decimal parsing)."""
        test_json = '{"price": 123.45, "quantity": 10}'

        result = HighPerformanceJSONHandler.loads(test_json, parser_number=True)

        assert isinstance(result["price"], Decimal)
        assert result["price"] == Decimal("123.45")
        assert isinstance(result["quantity"], Decimal)
        assert result["quantity"] == Decimal("10")

    def test_parser_number_false(self):
        """Test loads with parser_number=False (native types)."""
        test_json = '{"price": 123.45, "quantity": 10}'

        result = HighPerformanceJSONHandler.loads(test_json, parser_number=False)

        # Should use native types (int, float)
        assert isinstance(result["price"], float)
        assert result["price"] == 123.45
        assert isinstance(result["quantity"], int)
        assert result["quantity"] == 10

    @pytest.mark.skipif(not HAS_PENDULUM, reason="Pendulum not available")
    def test_datetime_parsing_with_pendulum(self, sample_datetime_strings):
        """Test datetime parsing when Pendulum is available."""
        for dt_string in sample_datetime_strings:
            data = {"timestamp": dt_string}
            json_str = json.dumps(data)

            result = HighPerformanceJSONHandler.loads(json_str, parse_datetime=True)

            if HighPerformanceJSONHandler._parse_datetime_in_object(dt_string):
                assert isinstance(result["timestamp"], datetime)
            else:
                assert isinstance(result["timestamp"], str)

    def test_datetime_parsing_disabled(self, sample_datetime_strings):
        """Test datetime parsing can be disabled."""
        dt_string = sample_datetime_strings[0]
        data = {"timestamp": dt_string}
        json_str = json.dumps(data)

        result = HighPerformanceJSONHandler.loads(json_str, parse_datetime=False)

        # Should remain as string
        assert isinstance(result["timestamp"], str)
        assert result["timestamp"] == dt_string

    def test_nested_datetime_parsing(self):
        """Test datetime parsing in nested structures."""
        data = {
            "user": {
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-02T13:30:00Z"
            },
            "events": [
                {"timestamp": "2024-01-03T14:45:00Z"},
                {"timestamp": "2024-01-04T15:15:00Z"}
            ]
        }
        json_str = json.dumps(data)

        result = HighPerformanceJSONHandler.loads(json_str, parse_datetime=True)

        # Check nested parsing worked (if datetime handler can parse these formats)
        if hasattr(result["user"]["created_at"], "year"):
            assert isinstance(result["user"]["created_at"], datetime)

    def test_bytes_input_handling(self):
        """Test handling of bytes input."""
        test_data = {"message": "hello"}
        json_bytes = json.dumps(test_data).encode('utf-8')

        # Test with parser_number=True
        result1 = HighPerformanceJSONHandler.loads(json_bytes, parser_number=True)
        assert result1["message"] == "hello"

        # Test with parser_number=False
        result2 = HighPerformanceJSONHandler.loads(json_bytes, parser_number=False)
        assert result2["message"] == "hello"

    def test_is_json_string_valid(self):
        """Test JSON string validation."""
        valid_json = '{"valid": true}'
        invalid_json = '{"invalid": true'

        assert HighPerformanceJSONHandler.is_json_string(valid_json) is True
        assert HighPerformanceJSONHandler.is_json_string(invalid_json) is False

    def test_is_json_string_non_string(self):
        """Test JSON validation with non-string input."""
        assert HighPerformanceJSONHandler.is_json_string(123) is False
        assert HighPerformanceJSONHandler.is_json_string(None) is False
        assert HighPerformanceJSONHandler.is_json_string([]) is False

    def test_sqlalchemy_model_serialization_mock(self):
        """Test SQLAlchemy model serialization with mock objects."""
        # Create a mock SQLAlchemy-like object
        class MockColumn:
            def __init__(self, name):
                self.name = name

        class MockRelationship:
            def __init__(self, key):
                self.key = key

        class MockMapper:
            def __init__(self):
                self.relationships = [MockRelationship("related_items")]

        class MockModel:
            def __init__(self):
                self.__table__ = type('MockTable', (), {
                    'columns': [MockColumn('id'), MockColumn('name')]
                })()
                self.__mapper__ = MockMapper()
                self.id = 1
                self.name = "test"
                self.related_items = [{"id": 2, "value": "related"}]

        mock_model = MockModel()

        result = HighPerformanceJSONHandler.dumps(mock_model)
        parsed = json.loads(result)

        assert "id" in parsed
        assert "name" in parsed
        assert parsed["id"] == 1
        assert parsed["name"] == "test"

    def test_depth_limiting(self):
        """Test serialization depth limiting."""
        # Create deeply nested structure
        deep_obj = {"level": 0}
        current = deep_obj

        for i in range(1, 10):
            current["nested"] = {"level": i}
            current = current["nested"]

        result = HighPerformanceJSONHandler.dumps(deep_obj)
        parsed = json.loads(result)

        # Should be serialized (depth limiting prevents infinite recursion)
        assert isinstance(parsed, dict)
        assert parsed["level"] == 0

    def test_error_handling_invalid_json(self):
        """Test error handling with invalid JSON."""
        invalid_json = '{"incomplete": '

        with pytest.raises((json.JSONDecodeError, ValueError)):
            HighPerformanceJSONHandler.loads(invalid_json)

    def test_convenience_alias(self):
        """Test that JSONHandler alias works."""
        assert JSONHandler == HighPerformanceJSONHandler

        # Test that it works the same way
        data = {"test": "value"}

        result1 = HighPerformanceJSONHandler.dumps(data)
        result2 = JSONHandler.dumps(data)

        assert result1 == result2

    def test_round_trip_consistency(self, sample_json_data):
        """Test that dumps -> loads preserves data (round trip)."""
        # Test with parser_number=True
        json_str = HighPerformanceJSONHandler.dumps(sample_json_data)
        recovered = HighPerformanceJSONHandler.loads(json_str, parser_number=False, parse_datetime=False)

        # Basic structure should be preserved
        assert recovered["string_field"] == sample_json_data["string_field"]
        assert recovered["boolean_field"] == sample_json_data["boolean_field"]
        assert recovered["null_field"] == sample_json_data["null_field"]
        assert recovered["array_field"] == sample_json_data["array_field"]

    def test_custom_serialization_handler(self):
        """Test custom objects with serialization handler."""
        # Test namedtuple serialization
        from collections import namedtuple
        Person = namedtuple('Person', ['name', 'age'])

        person = Person("John", 30)
        data = {"person": person}

        result = HighPerformanceJSONHandler.dumps(data)
        parsed = json.loads(result)

        assert "person" in parsed
        assert parsed["person"]["name"] == "John"
        assert parsed["person"]["age"] == 30

    def test_serialization_error_handling(self):
        """Test handling of non-serializable objects."""
        class NonSerializable:
            pass

        data = {"obj": NonSerializable()}

        with pytest.raises(TypeError):
            HighPerformanceJSONHandler.dumps(data)


@pytest.mark.performance
class TestJSONPerformanceIntegration:
    """Test JSON operations with performance monitoring."""

    def test_performance_monitoring_integration(self, mock_logger):
        """Test that performance monitoring doesn't break functionality."""
        # This test ensures the performance monitor decorator doesn't interfere
        data = {"test": "performance"}

        # Should work normally despite monitoring decorator
        json_str = HighPerformanceJSONHandler.dumps(data)
        result = HighPerformanceJSONHandler.loads(json_str)

        assert result == data

    def test_large_data_handling(self):
        """Test handling of larger data structures."""
        # Generate larger test data
        large_data = {
            "items": [{"id": i, "value": f"item_{i}"} for i in range(1000)],
            "metadata": {
                "count": 1000,
                "created": "2024-01-01T00:00:00Z",
                "type": "test_data"
            }
        }

        # Should handle large data without issues
        json_str = HighPerformanceJSONHandler.dumps(large_data)
        result = HighPerformanceJSONHandler.loads(json_str, parse_datetime=False)

        assert len(result["items"]) == 1000
        assert result["metadata"]["count"] == 1000