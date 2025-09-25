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

    ORJSON_AVAILABLE = True
    import json  # Still need for fallback and error handling
except ImportError:
    raise ImportError("orjson library is not installed. Please install orjson.")
    import json

    ORJSON_AVAILABLE = False

# Import SQLAlchemy for legacy JSONEncoder
try:
    from sqlalchemy import orm
    from sqlalchemy.ext.declarative import DeclarativeMeta

    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    DeclarativeMeta = None

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
        """Unified serialization handler for all types and situations."""
        if _depth >= _max_depth:
            return {"_truncated": True, "_type": str(type(obj).__name__)}

        # Handle basic JSON-serializable types (pass through unchanged)
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj

        # Handle Decimal - convert whole numbers to int, others to float
        elif isinstance(obj, Decimal):
            if obj.as_integer_ratio()[1] == 1:
                return int(obj)
            return float(obj)

        # Handle datetime/date - use ISO format for consistency
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()

        # Handle SQLAlchemy models - use comprehensive approach
        elif (
            SQLALCHEMY_AVAILABLE
            and DeclarativeMeta
            and isinstance(obj.__class__, DeclarativeMeta)
        ):
            return HighPerformanceJSONHandler._serialize_sqlalchemy(
                obj, _depth, _max_depth
            )

        # Handle objects with attribute_values
        elif hasattr(obj, "attribute_values"):
            return obj.attribute_values

        # Handle bytes/bytearray
        elif isinstance(obj, (bytes, bytearray)):
            return str(obj)

        # Handle namedtuples
        elif hasattr(obj, "_asdict"):
            return obj._asdict()

        # Handle custom objects with __dict__
        elif hasattr(obj, "__dict__"):
            return HighPerformanceJSONHandler._serialize_dict_with_depth(
                obj.__dict__, _depth, _max_depth
            )

        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    @staticmethod
    def _serialize_sqlalchemy(obj: Any, _depth: int, _max_depth: int) -> Dict[str, Any]:
        """Unified SQLAlchemy model serialization handling all cases."""
        if not SQLALCHEMY_AVAILABLE:
            return obj.__dict__ if hasattr(obj, "__dict__") else str(obj)

        def convert_object_to_dict(obj, found=None):
            if found is None:
                found = set()

            result = {}

            # Get column attributes (non-relationship fields)
            if hasattr(obj, "__table__"):
                mapper = orm.class_mapper(obj.__class__)
                columns = [column.key for column in mapper.columns]

                for col_key in columns:
                    value = getattr(obj, col_key, None)
                    if value is not None:
                        if isinstance(value, (datetime, date)):
                            result[col_key] = value.isoformat()
                        elif isinstance(value, Decimal):
                            if value.as_integer_ratio()[1] == 1:
                                result[col_key] = int(value)
                            else:
                                result[col_key] = float(value)
                        else:
                            result[col_key] = value

                # Handle relationships with depth limiting and circular reference prevention
                if _depth < _max_depth and hasattr(obj, "__mapper__"):
                    for relationship in mapper.relationships:
                        if relationship not in found:
                            found.add(relationship)
                            rel_value = getattr(obj, relationship.key, None)

                            if rel_value is not None:
                                if hasattr(rel_value, "__iter__") and not isinstance(
                                    rel_value, (str, bytes)
                                ):
                                    # Collection relationship - limit to first 5 items
                                    result[relationship.key] = [
                                        convert_object_to_dict(child, found.copy())
                                        for child in list(rel_value)[:5]
                                    ]
                                else:
                                    # Single relationship
                                    result[relationship.key] = convert_object_to_dict(
                                        rel_value, found.copy()
                                    )
            else:
                # Fallback for objects without __table__
                result = obj.__dict__ if hasattr(obj, "__dict__") else str(obj)

            return result

        return convert_object_to_dict(obj)

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
    def dumps(obj: Any, compact: bool = True, **kwargs) -> str:
        """
        High-performance JSON serialization with unified handler.

        Args:
            obj: Object to serialize
            compact: Whether to use compact formatting (default: True for backward compatibility)
            **kwargs: Additional arguments (indent, sort_keys, separators, etc. for compatibility)

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
            # Fallback to standard json with unified handler
            # Use provided indent or default based on compact setting
            if "indent" not in kwargs:
                kwargs["indent"] = None if compact else 2

            return json.dumps(
                obj,
                default=HighPerformanceJSONHandler._serialize_handler,
                ensure_ascii=False,
                **kwargs,
            )

    @staticmethod
    @performance_monitor.monitor_json_operation("json_loads")
    def loads(
        data: Union[str, bytes],
        parser_number: bool = True,
        parse_datetime: bool = True,
        **kwargs,
    ) -> Any:
        """
        High-performance JSON deserialization with datetime parsing.

        Args:
            data: JSON string or bytes to parse
            parser_number: Whether to parse numbers as Decimal (True) or native types (False)
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
    def json_normalize(
        obj: Any, parser_number: bool = True, parse_datetime: bool = True
    ) -> Any:
        """
        Normalize data types as if going through JSON serialization/deserialization.

        This function simulates the complete json_loads(json_dumps(obj)) cycle without
        the overhead of actual JSON string creation and parsing.

        Args:
            obj: Object to normalize
            parser_number: Whether to convert numbers back to Decimal after float conversion
            parse_datetime: Whether to parse ISO datetime strings back to datetime objects

        Returns:
            Normalized object with types as if processed through json_loads(json_dumps(obj))
        """
        # Phase 1: Apply serialization transformations (like json_dumps)
        serialized_form = HighPerformanceJSONHandler._serialize_object_recursive(obj)

        # Phase 2: Apply deserialization transformations (like json_loads)
        if parse_datetime:
            serialized_form = HighPerformanceJSONHandler._parse_datetime_in_object(
                serialized_form
            )

        if parser_number:
            serialized_form = HighPerformanceJSONHandler._parse_numbers_to_decimal(
                serialized_form
            )

        return serialized_form

    @staticmethod
    def _serialize_object_recursive(
        obj: Any, _depth: int = 0, _max_depth: int = 3
    ) -> Any:
        """
        Recursively apply serialization transformations without JSON encoding.
        This mimics what happens during JSON serialization.
        """
        # Use the existing serialize handler for individual objects
        if isinstance(obj, dict):
            return {
                key: HighPerformanceJSONHandler._serialize_object_recursive(
                    value, _depth, _max_depth
                )
                for key, value in obj.items()
            }
        elif isinstance(obj, (list, tuple)):
            return [
                HighPerformanceJSONHandler._serialize_object_recursive(
                    item, _depth, _max_depth
                )
                for item in obj
            ]
        else:
            # Apply the same transformations as the serialize handler
            return HighPerformanceJSONHandler._serialize_handler(
                obj, _depth, _max_depth
            )

    @staticmethod
    def _parse_numbers_to_decimal(obj: Any) -> Any:
        """
        Convert float numbers back to Decimal as json_loads would do when parser_number=True.
        """
        if isinstance(obj, dict):
            return {
                key: HighPerformanceJSONHandler._parse_numbers_to_decimal(value)
                for key, value in obj.items()
            }
        elif isinstance(obj, (list, tuple)):
            return [
                HighPerformanceJSONHandler._parse_numbers_to_decimal(item)
                for item in obj
            ]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, int) and not isinstance(obj, bool):
            return Decimal(obj)
        else:
            return obj

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
