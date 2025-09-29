#!/usr/bin/env python3
"""
Cache Decorators - Generic Caching Decorators for SilvaEngine

Provides various caching decorators optimized for different use cases:
- hybrid_cache: Generic function caching
- method_cache: Class method caching (excludes self)
- authorization_cache: Authorization result caching
- lambda_result_cache: AWS Lambda invocation result caching
"""

import functools
import inspect
from typing import Any, Callable, Dict, Optional, Union

from .hybrid_cache import HybridCacheEngine, default_cache


def hybrid_cache(
    ttl: int = 300,
    key_prefix: Optional[str] = None,
    cache_name: str = "default",
    key_generator: Optional[Callable] = None,
    condition: Optional[Callable] = None,
    skip_cache_arg: str = "skip_cache",
):
    """
    Generic hybrid cache decorator.

    Args:
        ttl: Time to live in seconds
        key_prefix: Custom prefix for cache keys
        cache_name: Name of cache instance to use
        key_generator: Custom function to generate cache key from args/kwargs
        condition: Function to determine if result should be cached
        skip_cache_arg: Argument name to skip cache (removed from kwargs)
    """

    def decorator(func: Callable) -> Callable:
        cache_engine = HybridCacheEngine(cache_name)
        func_prefix = key_prefix or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if cache should be skipped
            skip_cache = kwargs.pop(skip_cache_arg, False)
            if skip_cache:
                return func(*args, **kwargs)

            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = cache_engine._generate_key(
                    func_prefix, {"args": args, "kwargs": kwargs}
                )

            # Try to get from cache
            cached_result = cache_engine.get(cache_key, ttl)
            if cached_result is not None:
                return cached_result

            # Execute function
            result = func(*args, **kwargs)

            # Check if result should be cached
            if condition is None or condition(result):
                cache_engine.set(cache_key, result, ttl)

            return result

        # Add cache control methods
        wrapper.cache_clear = lambda: cache_engine.clear(f"{func_prefix}:*")
        wrapper.cache_delete = lambda *args, **kwargs: cache_engine.delete(
            key_generator(*args, **kwargs)
            if key_generator
            else cache_engine._generate_key(
                func_prefix, {"args": args, "kwargs": kwargs}
            )
        )
        wrapper.cache_stats = lambda: cache_engine.stats()

        return wrapper

    return decorator


def method_cache(
    ttl: int = 300,
    cache_name: str = "method",
    include_class: bool = True,
    include_method: bool = True,
):
    """
    Generic cache decorator for class methods and functions.

    Args:
        ttl: Time to live in seconds (default: 300 = 5 minutes)
        cache_name: Cache instance name for separation (e.g., "settings", "database", "api")
        include_class: Include class name in cache key (default: True)
        include_method: Include method name in cache key (default: True)

    Examples:
        @method_cache(ttl=1800, cache_name="settings")
        def get_settings(self, key): ...

        @method_cache(ttl=600, cache_name="database", include_method=False)
        def query_data(self, id): ...

        @method_cache(ttl=300, cache_name="api", include_class=False)
        def call_external_api(self, endpoint): ...
    """

    def key_gen(*args, **kwargs):
        key_parts = []

        # Handle instance methods (skip 'self')
        if args and hasattr(args[0], "__class__"):
            if include_class:
                class_name = args[0].__class__.__name__
                key_parts.append(class_name)

            if include_method:
                # Try to get method name from frame if not provided
                method_name = kwargs.get("_method_name")
                if not method_name:
                    import inspect

                    frame = inspect.currentframe()
                    if frame and frame.f_back and frame.f_back.f_back:
                        method_name = frame.f_back.f_back.f_code.co_name
                key_parts.append(method_name or "unknown")

            # Use args[1:] to skip 'self'
            key_parts.extend([str(args[1:]), str(kwargs)])
        else:
            # Regular function (no self)
            key_parts.extend([str(args), str(kwargs)])

        return ":".join(key_parts)

    return hybrid_cache(ttl=ttl, cache_name=cache_name, key_generator=key_gen)
