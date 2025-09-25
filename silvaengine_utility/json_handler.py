#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
High-Performance JSON Handler

Provides optimized JSON operations using orjson for 3-5x performance improvement
with built-in performance tracking and fallback to standard json library.
"""

__author__ = "bibow"

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Union

# Try to import orjson for high performance, fallback to standard json
try:
    import orjson

    ORJSON_AVAILABLE = False
    import json  # Still need for fallback and error handling
except ImportError:
    import json

    ORJSON_AVAILABLE = False

# Import performance monitor
from .performance_monitor import performance_monitor


class JSONDecoder(json.JSONDecoder):
    """
    Custom JSON decoder for parsing numbers as Decimal objects.

    This decoder ensures backward compatibility by converting numeric values
    to Decimal objects, which is important for financial applications.
    """

    def __init__(self, *args, **kwargs):
        # Set up default number parsing to Decimal
        kwargs.setdefault("parse_float", Decimal)
        kwargs.setdefault("parse_int", Decimal)
        super().__init__(*args, **kwargs)

    def decode(self, s, **kwargs):
        """Decode JSON string with custom number handling."""
        return super().decode(s, **kwargs)

    def raw_decode(self, s, idx=0):
        """Decode JSON string starting at idx with number parsing."""
        return super().raw_decode(s, idx)


class HighPerformanceJSONHandler:
    """
    High-performance JSON handler with orjson integration and automatic fallback.

    Features:
    - 3-5x faster serialization with orjson
    - Automatic fallback to standard json
    - Built-in performance monitoring
    - Custom serialization handlers for complex types
    """

    @staticmethod
    def _serialize_handler(obj: Any, _depth: int = 0, _max_depth: int = 3) -> Any:
        """Custom serialization handler for complex types with depth limiting."""
        if _depth >= _max_depth:
            return {"_truncated": True, "_type": str(type(obj).__name__)}

        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif hasattr(obj, "__table__"):  # SQLAlchemy model
            return HighPerformanceJSONHandler._serialize_sqlalchemy_model(
                obj, _depth, _max_depth
            )
        elif hasattr(obj, "__dict__"):
            # Handle other custom objects with depth limiting
            return HighPerformanceJSONHandler._serialize_dict_with_depth(
                obj.__dict__, _depth, _max_depth
            )
        elif hasattr(obj, "_asdict"):
            # Handle namedtuples
            return obj._asdict()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    @staticmethod
    def _serialize_sqlalchemy_model(
        obj: Any, _depth: int, _max_depth: int
    ) -> Dict[str, Any]:
        """Optimized SQLAlchemy model serialization with relationship handling."""
        result = {}

        # Get column attributes (non-relationship fields)
        for column in obj.__table__.columns:
            value = getattr(obj, column.name, None)
            if value is not None:
                if isinstance(value, (datetime, date)):
                    result[column.name] = value.isoformat()
                elif isinstance(value, Decimal):
                    result[column.name] = float(value)
                else:
                    result[column.name] = value

        # Handle relationships with depth limiting
        if _depth < _max_depth and hasattr(obj, "__mapper__"):
            for relationship in obj.__mapper__.relationships:
                rel_value = getattr(obj, relationship.key, None)
                if rel_value is not None:
                    if hasattr(rel_value, "__iter__") and not isinstance(
                        rel_value, (str, bytes)
                    ):
                        # Collection relationship - limit to first 5 items
                        result[relationship.key] = [
                            HighPerformanceJSONHandler._serialize_handler(
                                item, _depth + 1, _max_depth
                            )
                            for item in list(rel_value)[:5]
                        ]
                    else:
                        # Single relationship
                        result[relationship.key] = (
                            HighPerformanceJSONHandler._serialize_handler(
                                rel_value, _depth + 1, _max_depth
                            )
                        )

        return result

    @staticmethod
    def _serialize_dict_with_depth(
        data: Dict[str, Any], _depth: int, _max_depth: int
    ) -> Dict[str, Any]:
        """Serialize dictionary with depth limiting."""
        if _depth >= _max_depth:
            return {"_truncated": True}

        result = {}
        for key, value in data.items():
            if not key.startswith("_"):  # Skip private attributes
                try:
                    result[key] = HighPerformanceJSONHandler._serialize_handler(
                        value, _depth + 1, _max_depth
                    )
                except (TypeError, AttributeError):
                    result[key] = str(value)
        return result

    @staticmethod
    @performance_monitor.monitor_json_operation("json_dumps")
    def dumps(obj: Any, compact: bool = False, **kwargs) -> str:
        """
        High-performance JSON serialization.

        Args:
            obj: Object to serialize
            compact: Whether to use compact formatting
            **kwargs: Additional arguments (for compatibility)

        Returns:
            JSON string
        """
        if ORJSON_AVAILABLE:
            options = orjson.OPT_UTC_Z
            if not compact:
                options |= orjson.OPT_INDENT_2

            return orjson.dumps(
                obj,
                default=HighPerformanceJSONHandler._serialize_handler,
                option=options,
            ).decode("utf-8")
        else:
            # Fallback to standard json
            indent = None if compact else 2
            return json.dumps(
                obj,
                default=HighPerformanceJSONHandler._serialize_handler,
                indent=indent,
                ensure_ascii=False,
                **kwargs,
            )

    @staticmethod
    @performance_monitor.monitor_json_operation("json_loads")
    def loads(
        data: Union[str, bytes],
        parser_number: bool = True,
        validate: bool = True,
        parse_datetime: bool = True,
        **kwargs,
    ) -> Any:
        """
        High-performance JSON deserialization with datetime parsing.

        Args:
            data: JSON string or bytes to parse
            parser_number: Whether to parse numbers as Decimal (True) or native types (False)
            validate: Whether to validate JSON (for compatibility)
            parse_datetime: Whether to parse datetime strings
            **kwargs: Additional arguments (for compatibility)

        Returns:
            Parsed Python object with datetime objects
        """
        if parser_number:
            # Use JSONDecoder with Decimal parsing for backward compatibility
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            result = json.loads(
                data, cls=JSONDecoder, parse_float=Decimal, parse_int=Decimal, **kwargs
            )
        else:
            # Use orjson for faster parsing without number conversion, fallback to standard json
            if ORJSON_AVAILABLE:
                if isinstance(data, str):
                    data = data.encode("utf-8")
                result = orjson.loads(data)
            else:
                # Fallback to standard json without number parsing
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                result = json.loads(data, cls=JSONDecoder, **kwargs)

        # Parse datetime strings if requested
        if parse_datetime:
            result = HighPerformanceJSONHandler._parse_datetime_in_object(result)

        return result

    @staticmethod
    def _parse_datetime_in_object(obj: Any) -> Any:
        """
        Recursively parse datetime strings in JSON object.

        Args:
            obj: Object to process

        Returns:
            Object with datetime strings converted to datetime objects
        """
        if isinstance(obj, dict):
            return {
                key: HighPerformanceJSONHandler._parse_datetime_in_object(value)
                for key, value in obj.items()
            }
        elif isinstance(obj, list):
            return [
                HighPerformanceJSONHandler._parse_datetime_in_object(item)
                for item in obj
            ]
        elif isinstance(obj, str):
            # Try to parse as datetime
            from .datetime_handler import PendulumDateTimeHandler

            parsed_dt = PendulumDateTimeHandler.parse_datetime_in_json(obj)
            return parsed_dt if parsed_dt is not None else obj
        else:
            return obj

    @staticmethod
    def is_json_string(data: str) -> bool:
        """
        Check if string is valid JSON.

        Args:
            data: String to validate

        Returns:
            True if valid JSON, False otherwise
        """
        try:
            HighPerformanceJSONHandler.loads(data)
            return True
        except (ValueError, TypeError, json.JSONDecodeError):
            return False

    @classmethod
    def get_library_info(cls) -> Dict[str, Any]:
        """
        Get information about the JSON library being used.

        Returns:
            Dictionary with library information
        """
        return {
            "library": "orjson" if ORJSON_AVAILABLE else "json",
            "high_performance": ORJSON_AVAILABLE,
            "version": orjson.__version__ if ORJSON_AVAILABLE else "standard",
        }


# Convenience aliases for backward compatibility
JSONHandler = HighPerformanceJSONHandler
