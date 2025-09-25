#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

__all__ = [
    "utility",
    "http",
    "graphql",
    "authorizer",
    "common",
    "json_handler",
    "datetime_handler",
    "HighPerformanceJSONHandler",
    "JSONHandler",
    "JSONPerformanceMonitor",
    "performance_monitor",
    "PendulumDateTimeHandler",
    "DateTimeHandler",
    "parse_datetime_in_json",
    "parse_datetime",
    "ensure_datetime",
    "get_json_performance_stats",
    "reset_json_performance_stats",
    "get_json_performance_summary",
    "json_normalize",
    "Utility",
    "Struct",
]

from .authorizer import Authorizer
from .common import Common
from .datetime_handler import (
    DateTimeHandler,
    PendulumDateTimeHandler,
    ensure_datetime,
    parse_datetime,
    parse_datetime_in_json,
)
from .http import HttpResponse
from .json_handler import HighPerformanceJSONHandler, JSONHandler
from .performance_monitor import performance_monitor
from .utility import Struct, Utility

# Convenience exports for common functions
json_normalize = Utility.json_normalize

try:
    from .graphql_utils import JSON, Graphql
except ImportError:  # pragma: no cover - optional graphql dependency mismatch
    JSON = None
    Graphql = None
