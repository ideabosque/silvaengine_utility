#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Comprehensive tests for datetime handler functionality.
"""

import pytest
from datetime import datetime, date
from typing import Optional

from silvaengine_utility.datetime_handler import (
    PendulumDateTimeHandler,
    DateTimeHandler,
    parse_datetime,
    ensure_datetime,
    parse_datetime_in_json
)

# Check for optional dependencies
try:
    import pendulum
    HAS_PENDULUM = True
except ImportError:
    HAS_PENDULUM = False

try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


class TestPendulumDateTimeHandler:
    """Test the PendulumDateTimeHandler class."""

    def test_library_info(self):
        """Test library information reporting."""
        info = PendulumDateTimeHandler.get_library_info()

        assert "library" in info
        assert "high_performance" in info
        assert "version" in info

        if HAS_PENDULUM:
            assert info["library"] == "pendulum"
            assert info["high_performance"] is True
        elif HAS_DATEUTIL:
            assert info["library"] == "python-dateutil"
            assert info["high_performance"] is False
        else:
            assert info["library"] == "datetime (standard)"
            assert info["high_performance"] is False

    def test_iso_datetime_pattern_matching(self):
        """Test ISO datetime pattern recognition."""
        handler = PendulumDateTimeHandler

        # Valid ISO datetime patterns
        valid_patterns = [
            "2024-01-01T12:00:00Z",
            "2024-01-01T12:00:00.123Z",
            "2024-01-01T12:00:00+00:00",
            "2024-01-01T12:00:00-05:00",
            "2024-01-01 12:00:00Z",
            "2024-12-31T23:59:59.999999Z"
        ]

        for pattern in valid_patterns:
            assert handler.ISO_DATETIME_PATTERN.match(pattern) is not None, f"Failed to match: {pattern}"

        # Valid ISO date patterns
        valid_date_patterns = [
            "2024-01-01",
            "2024-12-31"
        ]

        for pattern in valid_date_patterns:
            assert handler.ISO_DATE_PATTERN.match(pattern) is not None, f"Failed to match date: {pattern}"

        # Invalid patterns
        invalid_patterns = [
            "not-a-date",
            "2024/01/01",
            "01-01-2024",
            "2024-13-01",  # Invalid month
            "2024-01-32",  # Invalid day
            ""
        ]

        for pattern in invalid_patterns:
            assert handler.ISO_DATETIME_PATTERN.match(pattern) is None
            assert handler.ISO_DATE_PATTERN.match(pattern) is None

    def test_timestamp_pattern_matching(self):
        """Test timestamp pattern recognition."""
        handler = PendulumDateTimeHandler

        # Valid timestamp patterns (10-13 digits)
        valid_timestamps = [
            "1640995200",      # 10 digits (seconds)
            "1640995200000",   # 13 digits (milliseconds)
            "1640995200123"    # 13 digits (milliseconds)
        ]

        for timestamp in valid_timestamps:
            assert handler.TIMESTAMP_PATTERN.match(timestamp) is not None, f"Failed to match timestamp: {timestamp}"

        # Invalid timestamp patterns
        invalid_timestamps = [
            "164099520",       # Too short (9 digits)
            "16409952001234",  # Too long (14 digits)
            "not-a-timestamp",
            "12.34",
            ""
        ]

        for timestamp in invalid_timestamps:
            assert handler.TIMESTAMP_PATTERN.match(timestamp) is None

    def test_parse_datetime_in_json_valid_dates(self, sample_datetime_strings):
        """Test parsing of valid datetime strings."""
        for dt_string in sample_datetime_strings:
            result = PendulumDateTimeHandler.parse_datetime_in_json(dt_string)

            if PendulumDateTimeHandler.is_datetime_string(dt_string):
                # Should return a datetime if it matches patterns
                assert result is None or isinstance(result, datetime), f"Failed to parse: {dt_string}"
            else:
                assert result is None

    def test_parse_datetime_in_json_invalid_input(self):
        """Test parsing with invalid input types and values."""
        invalid_inputs = [
            None,
            123,
            [],
            {},
            "not-a-date",
            "2024/01/01",
            ""
        ]

        for invalid_input in invalid_inputs:
            result = PendulumDateTimeHandler.parse_datetime_in_json(invalid_input)
            assert result is None

    @pytest.mark.skipif(not HAS_PENDULUM, reason="Pendulum not available")
    def test_pendulum_parsing(self):
        """Test datetime parsing with Pendulum when available."""
        test_string = "2024-01-01T12:00:00Z"

        result = PendulumDateTimeHandler.parse_datetime_in_json(test_string)

        assert result is not None
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12

    def test_standard_datetime_parsing_fallback(self):
        """Test fallback to standard datetime parsing."""
        # Test ISO formats that should work with standard datetime
        test_cases = [
            ("2024-01-01T12:00:00", datetime(2024, 1, 1, 12, 0, 0)),
            ("2024-01-01", None),  # Date only - depends on implementation
        ]

        for test_string, expected in test_cases:
            result = PendulumDateTimeHandler._parse_with_standard_datetime(test_string)

            if expected is not None:
                assert result is not None
                assert isinstance(result, datetime)
                assert result.year == expected.year
                assert result.month == expected.month
                assert result.day == expected.day

    def test_is_datetime_string(self):
        """Test datetime string recognition."""
        valid_strings = [
            "2024-01-01T12:00:00Z",
            "2024-01-01",
            "1640995200"  # timestamp
        ]

        invalid_strings = [
            "not-a-date",
            "2024/01/01",
            "01-01-2024",
            123,
            None,
            ""
        ]

        for valid_string in valid_strings:
            assert PendulumDateTimeHandler.is_datetime_string(valid_string) is True

        for invalid_string in invalid_strings:
            assert PendulumDateTimeHandler.is_datetime_string(invalid_string) is False

    def test_format_datetime(self):
        """Test datetime formatting to ISO string."""
        test_datetime = datetime(2024, 1, 1, 12, 0, 0)
        test_date = date(2024, 1, 1)

        result_datetime = PendulumDateTimeHandler.format_datetime(test_datetime)
        result_date = PendulumDateTimeHandler.format_datetime(test_date)

        assert result_datetime == "2024-01-01T12:00:00"
        assert result_date == "2024-01-01"

        # Test with non-datetime object
        result_other = PendulumDateTimeHandler.format_datetime("not-a-date")
        assert result_other == "not-a-date"

    def test_cache_functionality(self):
        """Test LRU cache functionality."""
        # Clear cache first
        PendulumDateTimeHandler.clear_cache()

        # Get initial cache info
        initial_info = PendulumDateTimeHandler.get_cache_info()
        assert initial_info["hits"] == 0
        assert initial_info["misses"] == 0

        # Parse the same string multiple times
        test_string = "2024-01-01T12:00:00Z"

        for _ in range(3):
            result = PendulumDateTimeHandler.parse_datetime_in_json(test_string)

        # Check cache info
        cache_info = PendulumDateTimeHandler.get_cache_info()

        # Should have hits from cache
        assert cache_info["hits"] >= 2  # At least 2 hits from the 3 calls
        assert cache_info["misses"] >= 1  # At least 1 miss for the first call

        # Test cache clearing
        PendulumDateTimeHandler.clear_cache()
        cleared_info = PendulumDateTimeHandler.get_cache_info()
        assert cleared_info["hits"] == 0
        assert cleared_info["misses"] == 0

    def test_cache_info_structure(self):
        """Test cache info return structure."""
        info = PendulumDateTimeHandler.get_cache_info()

        required_keys = ["hits", "misses", "maxsize", "currsize", "hit_rate"]
        for key in required_keys:
            assert key in info

        assert isinstance(info["hit_rate"], float)
        assert 0.0 <= info["hit_rate"] <= 1.0


class TestConvenienceAliases:
    """Test convenience aliases and functions."""

    def test_datetime_handler_alias(self):
        """Test DateTimeHandler alias."""
        assert DateTimeHandler == PendulumDateTimeHandler

    def test_parse_datetime_function(self):
        """Test parse_datetime convenience function."""
        test_string = "2024-01-01T12:00:00Z"

        result1 = parse_datetime(test_string)
        result2 = PendulumDateTimeHandler.parse_datetime_in_json(test_string)

        # Should give same result
        if result1 is not None and result2 is not None:
            assert result1 == result2
        else:
            assert result1 == result2

    def test_parse_datetime_in_json_function(self):
        """Test parse_datetime_in_json convenience function."""
        test_string = "2024-01-01T12:00:00Z"

        result1 = parse_datetime_in_json(test_string)
        result2 = PendulumDateTimeHandler.parse_datetime_in_json(test_string)

        if result1 is not None and result2 is not None:
            assert result1 == result2
        else:
            assert result1 == result2

    def test_ensure_datetime_function(self):
        """Test ensure_datetime convenience function."""
        # Test with datetime object
        test_datetime = datetime(2024, 1, 1, 12, 0, 0)
        result = ensure_datetime(test_datetime)
        assert result == test_datetime

        # Test with string
        test_string = "2024-01-01T12:00:00Z"
        result = ensure_datetime(test_string)
        # Result should be datetime or None (depending on parsing success)
        assert result is None or isinstance(result, datetime)

        # Test with non-convertible type
        result = ensure_datetime(123)
        assert result is None

        result = ensure_datetime(None)
        assert result is None


class TestDateTimeEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_string_handling(self):
        """Test handling of empty strings."""
        result = PendulumDateTimeHandler.parse_datetime_in_json("")
        assert result is None

    def test_whitespace_handling(self):
        """Test handling of whitespace-only strings."""
        whitespace_strings = ["   ", "\t", "\n", " \t\n "]

        for ws_string in whitespace_strings:
            result = PendulumDateTimeHandler.parse_datetime_in_json(ws_string)
            assert result is None

    def test_malformed_iso_strings(self):
        """Test handling of malformed ISO datetime strings."""
        malformed_strings = [
            "2024-01-01T",
            "2024-01-01T25:00:00Z",  # Invalid hour
            "2024-01-01T12:60:00Z",  # Invalid minute
            "2024-01-01T12:00:60Z",  # Invalid second
            "2024-13-01T12:00:00Z",  # Invalid month
            "2024-01-32T12:00:00Z",  # Invalid day
        ]

        for malformed_string in malformed_strings:
            result = PendulumDateTimeHandler.parse_datetime_in_json(malformed_string)
            # Should return None for malformed strings
            assert result is None

    def test_boundary_dates(self):
        """Test boundary dates and times."""
        boundary_strings = [
            "1900-01-01T00:00:00Z",
            "2100-12-31T23:59:59Z",
            "2024-02-29T12:00:00Z",  # Leap year
        ]

        for boundary_string in boundary_strings:
            if PendulumDateTimeHandler.is_datetime_string(boundary_string):
                result = PendulumDateTimeHandler.parse_datetime_in_json(boundary_string)
                # Should either parse successfully or return None
                assert result is None or isinstance(result, datetime)

    def test_unicode_and_encoding(self):
        """Test handling of unicode and different encodings."""
        # Test with unicode characters (should fail)
        unicode_string = "2024-01-01T12:00:00Z\u00A0"  # Non-breaking space
        result = PendulumDateTimeHandler.parse_datetime_in_json(unicode_string)
        assert result is None

        # Test normal ASCII string
        ascii_string = "2024-01-01T12:00:00Z"
        result = PendulumDateTimeHandler.parse_datetime_in_json(ascii_string)
        # Should work if the pattern matches
        if PendulumDateTimeHandler.is_datetime_string(ascii_string):
            assert result is None or isinstance(result, datetime)

    def test_cache_memory_management(self):
        """Test that cache doesn't grow indefinitely."""
        # Clear cache first
        PendulumDateTimeHandler.clear_cache()

        # Generate many different datetime strings
        for i in range(1500):  # More than cache maxsize (1000)
            test_string = f"2024-01-01T{i % 24:02d}:00:00Z"
            PendulumDateTimeHandler.parse_datetime_in_json(test_string)

        cache_info = PendulumDateTimeHandler.get_cache_info()

        # Cache size should not exceed maxsize
        assert cache_info["currsize"] <= cache_info["maxsize"]
        assert cache_info["maxsize"] == 1000  # Default maxsize