#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import functools
import inspect
import threading
from typing import Any, Callable, Dict, Optional


class ObjectCacheEngine:
    """
    Thread-safe object cache for dynamically imported modules and classes.

    Cache keys are formatted as: module_name:class_name:function_name
    Cache has no expiration time (permanent cache).
    """

    _cache: Dict[str, Any] = {}
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def _generate_key(
        cls,
        module_name: str,
        class_name: Optional[str],
        function_name: str,
    ) -> str:
        """
        Generate cache key from module, class and function names.

        Args:
            module_name: Name of the module
            class_name: Optional name of the class
            function_name: Name of the function/method

        Returns:
            Cache key string
        """
        if class_name:
            return f"{module_name}:{class_name}:{function_name}"
        return f"{module_name}:{function_name}"

    @classmethod
    def get(
        cls,
        module_name: str,
        class_name: Optional[str],
        function_name: str,
    ) -> Optional[Any]:
        """
        Get cached object if available.

        Args:
            module_name: Name of the module
            class_name: Optional name of the class
            function_name: Name of the function/method

        Returns:
            Cached object or None if not found
        """
        key = cls._generate_key(module_name, class_name, function_name)

        with cls._lock:
            return cls._cache.get(key)

    @classmethod
    def set(
        cls,
        module_name: str,
        class_name: Optional[str],
        function_name: str,
        obj: Any,
    ) -> None:
        """
        Cache an object with the given key.

        Args:
            module_name: Name of the module
            class_name: Optional name of the class
            function_name: Name of the function/method
            obj: Object to cache
        """
        key = cls._generate_key(module_name, class_name, function_name)

        with cls._lock:
            cls._cache[key] = obj

    @classmethod
    def clear(cls) -> None:
        """
        Clear all cached objects.
        """
        with cls._lock:
            cls._cache.clear()

    @classmethod
    def size(cls) -> int:
        """
        Get the number of cached objects.

        Returns:
            Number of cached objects
        """
        with cls._lock:
            return len(cls._cache)

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        with cls._lock:
            return {
                "size": len(cls._cache),
                "keys": list(cls._cache.keys()),
            }

    @classmethod
    def remove(
        cls,
        module_name: str,
        class_name: Optional[str],
        function_name: str,
    ) -> bool:
        """
        Remove a specific object from cache.

        Args:
            module_name: Name of the module
            class_name: Optional name of the class
            function_name: Name of the function/method

        Returns:
            True if object was removed, False if not found
        """
        key = cls._generate_key(module_name, class_name, function_name)

        with cls._lock:
            if key in cls._cache:
                del cls._cache[key]
                return True
            return False
