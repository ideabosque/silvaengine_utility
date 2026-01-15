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
from .object_cache import ObjectCacheEngine


def hybrid_cache(
    ttl: int = 300,
    key_prefix: Optional[str] = None,
    cache_name: str = "default",
    key_generator: Optional[Callable] = None,
    condition: Optional[Callable] = None,
    skip_cache_arg: str = "skip_cache",
    cache_enabled: Union[bool, Callable[[], bool]] = True,
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
        cache_enabled: Boolean or callable that returns boolean to enable/disable cache
    """

    def decorator(func: Callable) -> Callable:
        cache_engine = HybridCacheEngine(cache_name)
        func_prefix = key_prefix or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if cache is enabled (support both bool and callable)
            is_cache_enabled = (
                cache_enabled() if callable(cache_enabled) else cache_enabled
            )
            if not is_cache_enabled:
                return func(*args, **kwargs)

            # Check if cache should be skipped
            skip_cache = kwargs.pop(skip_cache_arg, False)
            if skip_cache:
                return func(*args, **kwargs)

            # Generate cache key
            if key_generator:
                key_data = key_generator(*args, **kwargs)
                cache_key = cache_engine._generate_key(func_prefix, key_data)
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
            cache_engine._generate_key(
                func_prefix,
                key_generator(*args, **kwargs)
                if key_generator
                else {"args": args, "kwargs": kwargs},
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
    cache_enabled: Union[bool, Callable[[], bool]] = True,
):
    """
    Generic cache decorator for class methods and functions.

    Args:
        ttl: Time to live in seconds (default: 300 = 5 minutes)
        cache_name: Cache instance name for separation (e.g., "settings", "database", "api")
        include_class: Include class name in cache key (default: True)
        include_method: Include method name in cache key (default: True)
        cache_enabled: Boolean or callable that returns boolean to enable/disable cache.
                      When callable, it is evaluated at runtime on each call.

    Examples:
        @method_cache(ttl=1800, cache_name="settings")
        def get_settings(self, key): ...

        @method_cache(ttl=600, cache_name="database", include_method=False)
        def query_data(self, id): ...

        @method_cache(ttl=300, cache_name="api", include_class=False)
        def call_external_api(self, endpoint): ...

        # With cache_enabled flag (callable for runtime evaluation)
        @method_cache(ttl=300, cache_enabled=Config.is_cache_enabled)
        def get_data(self, id): ...
    """

    def key_gen(*args, **kwargs):
        key_parts = []

        # Handle instance methods (skip 'self')
        # Check if first arg is likely 'self' - should have __dict__ or be a class instance
        # Exclude primitive types (str, int, float, bool, etc.) and built-in types
        is_instance_method = (
            args
            and hasattr(args[0], "__class__")
            and hasattr(args[0], "__dict__")
            and not isinstance(args[0], (str, int, float, bool, bytes, type(None)))
        )

        if is_instance_method:
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

    return hybrid_cache(
        ttl=ttl, cache_name=cache_name, key_generator=key_gen, cache_enabled=cache_enabled
    )


def object_cache(func: Callable) -> Callable:
    """
    Decorator to cache dynamically imported objects with thread safety.

    This decorator wraps functions that perform dynamic imports to cache
    the imported module/class/function, avoiding repeated import operations.

    Cache key format: module_name:class_name:function_name
    Cache has no expiration time (permanent cache).

    This is a parameterless decorator - it does not accept any arguments.

    Usage:
        @object_cache
        def import_dynamically(module_name, function_name, class_name=None, constructor_parameters=None):
            # Your import logic here
            return imported_object

    The decorator automatically extracts cache key components from kwargs:
    - module_name: Required, name of the module
    - function_name: Required, name of the function/method
    - class_name: Optional, name of the class containing the method

    Returns:
        Decorated function that uses cached objects
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        def get_invoker(*args, **kwargs):
            module_name = kwargs.get("module_name", "")
            function_name = kwargs.get("function_name", "")
            class_name = kwargs.get("class_name")

            if not module_name or not function_name:
                raise ValueError("module_name and function_name are required")

            logger = kwargs.get("logger")

            try:
                cached_object = ObjectCacheEngine.get(
                    module_name, class_name, function_name
                )

                if cached_object is not None:
                    if logger and hasattr(logger, "debug"):
                        logger.debug(
                            f"ObjectCacheEngine HIT: {module_name}:{class_name}:{function_name}"
                        )
                    return cached_object

                if logger and hasattr(logger, "debug"):
                    logger.debug(
                        f"ObjectCacheEngine MISS: {module_name}:{class_name}:{function_name}"
                    )

                invoker = func(*args, **kwargs)

                if invoker is not None:
                    ObjectCacheEngine.set(
                        module_name, class_name, function_name, invoker
                    )

                    if logger and hasattr(logger, "debug"):
                        logger.debug(
                            f"ObjectCacheEngine SET: {module_name}:{class_name}:{function_name}"
                        )

                return invoker

            except Exception as e:
                if logger and hasattr(logger, "error"):
                    logger.error(
                        f"ObjectCacheEngine error for {module_name}:{class_name}:{function_name}: {e}"
                    )
                raise

        try:
            invoker = get_invoker(*args, **kwargs)
            parameters = kwargs.get("constructor_parameters")

            if type(parameters) is dict:
                is_instance_method = not (
                    inspect.isfunction(invoker)
                    or (
                        inspect.ismethod(invoker)
                        and hasattr(invoker, "__self__")
                        and inspect.isclass(invoker.__self__)
                    )
                ) and inspect.ismethod(invoker)

                if is_instance_method:
                    invoker_object = invoker.__self__
                    invoker_object.__init__(**parameters)
            return invoker
        except Exception as e:
            raise e

    return wrapper
