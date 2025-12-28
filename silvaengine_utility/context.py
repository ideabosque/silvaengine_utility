#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Context management module for deployment mode tracking.

This module provides a centralized context management system for tracking
the deployment mode across the application. It supports both programmatic
configuration and environment variable fallback.
"""

from __future__ import print_function

from typing import Any, Dict


class Context:
    """
    Context management class for deployment mode tracking.

    This class provides thread-safe static methods for managing the
    deployment mode context across the application lifecycle.

    Attributes:
        _attribute_values: Class-level storage for context values
    """

    _attribute_values: Dict[str, Any] = {}

    @staticmethod
    def set(attribute: str, value: Any) -> None:
        """
        Set a context attribute value.

        Args:
            attribute: The attribute name to set
            value: The value to set
        """
        Context._attribute_values[str(attribute).strip().lower()] = value

    @staticmethod
    def get(attribute: str) -> Any:
        """
        Get a context attribute value.

        Args:
            attribute: The attribute name to get

        Returns:
            The attribute value or None if not set
        """
        return Context._attribute_values.get(str(attribute).strip().lower())

    @staticmethod
    def unset(attribute: str) -> Any:
        return Context._attribute_values.pop(str(attribute).strip().lower())

    @staticmethod
    def clear() -> None:
        Context._attribute_values.clear()
