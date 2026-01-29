#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict, Optional, Union

from .datetime_handler import PendulumDateTimeHandler
from .json_handler import HighPerformanceJSONHandler
from .performance_monitor import performance_monitor

_JSON_HANDLER = HighPerformanceJSONHandler()
_DATETIME_HANDLER = PendulumDateTimeHandler()


class Serializer(object):
    json_handler = _JSON_HANDLER
    datetime_handler = _DATETIME_HANDLER
    performance_monitor = performance_monitor

    @staticmethod
    def is_json_string(string: str) -> bool:
        """Check if string is valid JSON using high-performance handler."""
        return Serializer.json_handler.is_json_string(string)

    @staticmethod
    def json_dumps(data: Any, **kwargs: Dict[str, Any]) -> str:
        # Use consistent formatting with original jsonencode behavior
        defaults = {
            "compact": False,
            "indent": 2,
            "sort_keys": True,
            "separators": (",", ": "),
        }
        defaults.update(kwargs)
        return Serializer.json_handler.dumps(data, **defaults)

    @staticmethod
    def json_loads(
        data: Union[str, bytes],
        parser_number: bool = True,
        parse_datetime: bool = True,
        **kwargs: Dict[str, Any],
    ) -> Any:
        return Serializer.json_handler.loads(
            data, parser_number=parser_number, parse_datetime=parse_datetime, **kwargs
        )

    @staticmethod
    def json_normalize(
        data: Any, parser_number: bool = True, parse_datetime: bool = True
    ) -> Any:
        """
        Normalize data types as if going through JSON serialization/deserialization.


        This function simulates json_loads(json_dumps(obj)) without the overhead of
        actual JSON string creation and parsing.

        Args:
            data: Object to normalize
            parser_number: Whether to convert numbers to Decimal after float conversion (default: True)
            parse_datetime: Whether to parse ISO datetime strings back to datetime objects (default: True)

        Returns:
            Normalized object with types as if processed through json_loads(json_dumps(obj))

        Examples:
            # Normalize mixed data types
            data = {
                "amount": Decimal("100.50"),
                "created_at": datetime.now(),
                "items": [Decimal("10"), Decimal("20.5")]
            }
            normalized = Serializer.json_normalize(data)
            # Result: Decimal -> float -> Decimal, datetime -> ISO string -> datetime
        """
        return Serializer.json_handler.json_normalize(
            data, parser_number=parser_number, parse_datetime=parse_datetime
        )

    @staticmethod
    def get_library_info() -> Dict[str, Any]:
        """Get information about performance libraries being used."""
        return {
            "json": Serializer.json_handler.get_library_info(),
            "datetime": Serializer.datetime_handler.get_library_info(),
        }
