#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

__all__ = [
    "utility",
    "http",
    "graphql",
    "authorizer",
    "serializer",
    "invoker",
    "database",
    "json_handler",
    "datetime_handler",
    "cache",
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
    "convert_decimal_to_number",
    "Utility",
    "Struct",
    "HybridCacheEngine",
    "hybrid_cache",
    "method_cache",
    "SettingsQueueManager",
    "settings_queue_producer",
]

from .authorizer import Authorizer
from .cache import (
    HybridCacheEngine,
    hybrid_cache,
    method_cache,
)
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
from .serializer import Serializer
from .graphql import Graphql, JSON
from .invoker import Invoker
from .database import Database

# Convenience exports for common functions
json_normalize = Serializer.json_normalize
convert_decimal_to_number = HighPerformanceJSONHandler.convert_decimal_to_number

# try:
#     from .graphql import JSON, Graphql, SettingsQueueManager, settings_queue_producer
# except ImportError:  # pragma: no cover - optional graphql dependency mismatch
#     JSON = None
#     Graphql = None
#     SettingsQueueManager = None
#     settings_queue_producer = None
