"""
SilvaEngine Cache Module - Hybrid Redis/Disk Caching System

Provides high-performance caching with Redis primary and disk fallback,
optimized for AWS Lambda serverless environments.

Core Decorators:
- @hybrid_cache()         - Generic function caching
- @method_cache()         - Generic method/function caching with flexible options

Usage:
    from silvaengine_utility import method_cache, hybrid_cache

    class MyService:
        @method_cache(ttl=1800, cache_name="settings")
        def get_settings(self, key): ...

        @method_cache(ttl=600, cache_name="database", include_method=False)
        def get_data(self, id): ...
"""

from .hybrid_cache import HybridCacheEngine, default_cache
from .decorators import (
    hybrid_cache,
    method_cache
)

__all__ = [
    'HybridCacheEngine',
    'default_cache',
    'hybrid_cache',
    'method_cache'
]