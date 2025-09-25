#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
High-Performance DateTime Handler

Provides optimized datetime parsing using Pendulum for 2-3x performance improvement
with caching and fallback to python-dateutil.
"""

__author__ = "bibow"

import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Optional, Union

# Try to import pendulum for high performance, fallback to dateutil
try:
    import pendulum

    PENDULUM_AVAILABLE = True
except ImportError:
    PENDULUM_AVAILABLE = False
    try:
        from dateutil import parser as dateutil_parser

        DATEUTIL_AVAILABLE = True
    except ImportError:
        DATEUTIL_AVAILABLE = False


class PendulumDateTimeHandler:
    """
    High-performance datetime handler with Pendulum integration and automatic fallback.

    Features:
    - 2-3x faster datetime parsing with Pendulum
    - LRU cache for repeated datetime strings
    - Pre-compiled regex patterns for datetime recognition
    - Automatic fallback to dateutil or standard datetime
    """

    # Pre-compiled regex patterns for common datetime formats
    ISO_DATETIME_PATTERN = re.compile(
        r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
    )

    ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    TIMESTAMP_PATTERN = re.compile(
        r"^\d{10,13}$"
    )  # Unix timestamp (seconds or milliseconds)

    @classmethod
    @lru_cache(maxsize=1000)
    def parse_datetime_in_json(cls, value: str) -> Optional[datetime]:
        """
        Parse datetime string with caching for performance.

        Args:
            value: String value to parse as datetime

        Returns:
            Parsed datetime object or None if parsing fails
        """
        if not isinstance(value, str):
            return None

        # Quick pattern matching for performance
        if not (
            cls.ISO_DATETIME_PATTERN.match(value)
            or cls.ISO_DATE_PATTERN.match(value)
            or cls.TIMESTAMP_PATTERN.match(value)
        ):
            return None

        try:
            if PENDULUM_AVAILABLE:
                # Use Pendulum for high performance
                parsed = pendulum.parse(value)
                # Convert to standard datetime for compatibility
                return (
                    parsed.naive()
                    if parsed.timezone is None
                    else parsed.in_timezone("UTC").naive()
                )
            elif DATEUTIL_AVAILABLE:
                # Fallback to dateutil
                return dateutil_parser.parse(value)
            else:
                # Last resort: try standard datetime for ISO format
                return cls._parse_with_standard_datetime(value)
        except (ValueError, TypeError, Exception):
            return None

    @staticmethod
    def _parse_with_standard_datetime(value: str) -> Optional[datetime]:
        """Parse datetime using standard library as last resort."""
        try:
            # Try common ISO formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    @classmethod
    def is_datetime_string(cls, value: str) -> bool:
        """
        Check if string looks like a datetime.

        Args:
            value: String to check

        Returns:
            True if string appears to be a datetime
        """
        if not isinstance(value, str):
            return False

        return bool(
            cls.ISO_DATETIME_PATTERN.match(value)
            or cls.ISO_DATE_PATTERN.match(value)
            or cls.TIMESTAMP_PATTERN.match(value)
        )

    @classmethod
    def format_datetime(cls, dt: Union[datetime, date]) -> str:
        """
        Format datetime object to ISO string.

        Args:
            dt: Datetime or date object

        Returns:
            ISO formatted string
        """
        if isinstance(dt, datetime):
            return dt.isoformat()
        elif isinstance(dt, date):
            return dt.isoformat()
        else:
            return str(dt)

    @classmethod
    def get_library_info(cls) -> dict:
        """
        Get information about the datetime library being used.

        Returns:
            Dictionary with library information
        """
        if PENDULUM_AVAILABLE:
            import pendulum

            return {
                "library": "pendulum",
                "version": pendulum.__version__,
                "high_performance": True,
            }
        elif DATEUTIL_AVAILABLE:
            return {
                "library": "python-dateutil",
                "version": "unknown",
                "high_performance": False,
            }
        else:
            return {
                "library": "datetime (standard)",
                "version": "standard",
                "high_performance": False,
            }

    @classmethod
    def clear_cache(cls):
        """Clear the LRU cache for datetime parsing."""
        cls.parse_datetime_in_json.cache_clear()

    @classmethod
    def get_cache_info(cls) -> dict:
        """Get cache statistics."""
        cache_info = cls.parse_datetime_in_json.cache_info()
        return {
            "hits": cache_info.hits,
            "misses": cache_info.misses,
            "maxsize": cache_info.maxsize,
            "currsize": cache_info.currsize,
            "hit_rate": (
                cache_info.hits / (cache_info.hits + cache_info.misses)
                if (cache_info.hits + cache_info.misses) > 0
                else 0.0
            ),
        }


# Convenience aliases
DateTimeHandler = PendulumDateTimeHandler
parse_datetime = PendulumDateTimeHandler.parse_datetime_in_json


def ensure_datetime(value: Any) -> Optional[datetime]:
    """
    Ensure value is a datetime object.

    Args:
        value: Value to convert to datetime

    Returns:
        Datetime object or None if conversion fails
    """
    if isinstance(value, datetime):
        return value
    elif isinstance(value, str):
        return PendulumDateTimeHandler.parse_datetime_in_json(value)
    else:
        return None


def parse_datetime_in_json(value: str) -> Optional[datetime]:
    """
    Parse datetime string in JSON context.

    Args:
        value: String to parse

    Returns:
        Parsed datetime or None
    """
    return PendulumDateTimeHandler.parse_datetime_in_json(value)
