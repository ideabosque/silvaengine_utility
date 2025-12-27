#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bl"

import functools
import os
import queue
import threading
import time
import uuid

import graphene
from graphql import parse
from graphql.language import ast

from .invoker import Invoker
from .serializer import Serializer
from .utility import Utility

INTROSPECTION_QUERY = """
query IntrospectionQuery {
    __schema {
        queryType { name }
        mutationType { name }
        subscriptionType { name }
        types {
            kind
            name
            fields {
                name
                args {
                    name
                    type {
                        name
                        kind
                        ofType {
                            name
                            kind
                            ofType {
                                name
                                kind
                            }
                        }
                    }
                }
                type {
                    name
                    kind
                    ofType {
                        name
                        kind
                    }
                }
            }
        }
    }
}"""


class QueueManager:
    """
    Thread-safe queue manager for temporary storage of settings data.

    This manager provides a centralized queue for storing settings information
    that can be consumed by BaseModel subclasses. It ensures thread safety and
    proper lifecycle management of the temporary storage.

    Attributes:
        _instance: Singleton instance of the queue manager
        _lock: Thread lock for singleton pattern
        _queue: Thread-safe queue for storing settings
        _queue_lock: Lock for queue operations
        _max_size: Maximum queue size
        _retention_ttl: Time-to-live for items in the queue (seconds)
        _metadata: Dictionary storing item metadata with timestamps
        _metadata_lock: Lock for metadata operations
        _enabled: Flag to enable/disable queue operations
        _cleanup_interval: Interval for cleanup operations (seconds)
        _last_cleanup: Timestamp of last cleanup
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(QueueManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._queue = queue.Queue(maxsize=1000)
        self._queue_lock = threading.RLock()
        self._max_size = 1000
        self._retention_ttl = int(os.getenv("SETTINGS_QUEUE_TTL", "3600"))
        self._metadata = {}
        self._metadata_lock = threading.RLock()
        self._enabled = os.getenv("ENVIRONMENT", "development") == "production"
        self._cleanup_interval = int(
            os.getenv("SETTINGS_QUEUE_CLEANUP_INTERVAL", "300")
        )
        self._last_cleanup = time.time()
        self._initialized = True

    def is_enabled(self):
        """Check if queue operations are enabled."""
        return self._enabled

    def enqueue(self, settings_data, logger=None):
        """
        Enqueue settings data with metadata.

        Args:
            settings_data: Dictionary containing settings information
            logger: Logger instance for logging operations

        Returns:
            str: Unique identifier for the enqueued item
        """
        if not self._enabled:
            return None

        item_id = str(uuid.uuid4())
        timestamp = time.time()

        with self._queue_lock:
            try:
                if self._queue.full():
                    self._cleanup_expired_items(logger)

                queue_item = {
                    "id": item_id,
                    "data": settings_data,
                    "timestamp": timestamp,
                }
                self._queue.put_nowait(queue_item)

                with self._metadata_lock:
                    self._metadata[item_id] = {
                        "timestamp": timestamp,
                        "consumed": False,
                    }

                if logger:
                    logger.info(
                        f"Settings enqueued: id={item_id}, "
                        f"timestamp={timestamp}, queue_size={self._queue.qsize()}"
                    )

                return item_id
            except queue.Full:
                if logger:
                    logger.error(
                        f"Failed to enqueue settings: queue is full (size={self._queue.qsize()})"
                    )
                return None
            except Exception as e:
                if logger:
                    logger.error(f"Failed to enqueue settings: {str(e)}")
                return None

    def dequeue(self, logger=None):
        """
        Dequeue settings data.

        Args:
            logger: Logger instance for logging operations

        Returns:
            dict: Dequeued settings data or None if queue is empty
        """
        if not self._enabled:
            return None

        with self._queue_lock:
            try:
                item = self._queue.get_nowait()

                with self._metadata_lock:
                    if item["id"] in self._metadata:
                        self._metadata[item["id"]]["consumed"] = True

                if logger:
                    logger.info(
                        f"Settings dequeued: id={item['id']}, "
                        f"timestamp={item['timestamp']}, queue_size={self._queue.qsize()}"
                    )

                return item
            except queue.Empty:
                return None
            except Exception as e:
                if logger:
                    logger.error(f"Failed to dequeue settings: {str(e)}")
                return None

    def _cleanup_expired_items(self, logger=None):
        """
        Remove expired items from the queue and metadata.

        Args:
            logger: Logger instance for logging operations
        """
        current_time = time.time()
        expired_count = 0

        with self._metadata_lock:
            expired_ids = [
                item_id
                for item_id, meta in self._metadata.items()
                if current_time - meta["timestamp"] > self._retention_ttl
            ]

            for item_id in expired_ids:
                del self._metadata[item_id]
                expired_count += 1

        if expired_count > 0 and logger:
            logger.info(f"Cleaned up {expired_count} expired items from metadata")

        self._last_cleanup = current_time

    def get_queue_size(self):
        """Get current queue size."""
        with self._queue_lock:
            return self._queue.qsize()

    def get_metadata_stats(self):
        """
        Get metadata statistics.

        Returns:
            dict: Statistics about the queue metadata
        """
        with self._metadata_lock:
            total_items = len(self._metadata)
            consumed_items = sum(
                1 for meta in self._metadata.values() if meta["consumed"]
            )
            pending_items = total_items - consumed_items

            return {
                "total_items": total_items,
                "consumed_items": consumed_items,
                "pending_items": pending_items,
                "queue_size": self.get_queue_size(),
                "retention_ttl": self._retention_ttl,
            }

    def clear(self, logger=None):
        """
        Clear all items from the queue and metadata.

        Args:
            logger: Logger instance for logging operations
        """
        with self._queue_lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

        with self._metadata_lock:
            cleared_count = len(self._metadata)
            self._metadata.clear()

        if logger:
            logger.info(f"Cleared {cleared_count} items from queue and metadata")


def graphql_service_initialization(original_function):
    """
    Decorator to intercept Graphql class initialization and queue settings data.

    This decorator intercepts the __init__ method of the Graphql class and
    enqueues the settings data for consumption by BaseModel subclasses.
    The queue operations are only enabled in production environment.

    Args:
        original_function: The __init__ method to decorate

    Returns:
        callable: Wrapped function that enqueues settings data

    Usage:
        @settings_queue_producer
        def __init__(self, logger, **setting):
            self.logger = logger
            self.setting = setting
    """

    @functools.wraps(original_function)
    def wrapper_function(self, logger, **setting):
        queue_manager = QueueManager()

        if queue_manager.is_enabled():
            item_id = queue_manager.enqueue(setting, logger)

            if item_id and logger:
                logger.info(f"Settings queued via producer decorator: id={item_id}.")

        return original_function(self, logger, **setting)

    return wrapper_function


class Graphql(object):
    # Parse the graphql request's body to AST and extract fields from the AST
    @graphql_service_initialization
    def __init__(self, logger, **setting):
        self.logger = logger
        self.setting = setting

    def execute(self, schema, **params):
        try:
            context = {
                "logger": self.logger,
                "setting": self.setting,
                "endpoint_id": params.get("endpoint_id"),
                "connection_id": params.get("connection_id"),
            }

            if params.get("custom_headers"):
                context = dict(context, **params["custom_headers"])

            if params.get("context"):
                context = dict(context, **params["context"])

            query = params.get("query")

            if not query:
                return Graphql.error_response("Invalid operations.")

            execution_result = schema.execute(
                query,
                context_value=context,
                variable_values=params.get("variables", {}),
                operation_name=params.get("operation_name"),
            )

            if execution_result:
                if execution_result.data:
                    return Graphql.success_response(execution_result.data)
                elif execution_result.errors:
                    return Graphql.error_response(
                        [Utility.format_error(e) for e in execution_result.errors], 500
                    )
                elif execution_result.invalid:
                    return Graphql.error_response("Invalid execution result.", 500)

            return Graphql.error_response("Uncaught execution error.", 500)
        except Exception as e:
            return Graphql.error_response(str(e), 500)

    @staticmethod
    def success_response(data):
        return Graphql._format_response(data)

    @staticmethod
    def error_response(errors, status_code=400):
        return Graphql._format_response({"errors": errors}, status_code)

    @staticmethod
    def _format_response(data, status_code=200):
        return {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
            "body": Serializer.json_dumps(data),
        }

    @staticmethod
    def execute_graphql_query(
        context,
        funct,
        query,
        variables={},
        aws_lambda=None,
    ):
        params = {
            "query": query,
            "variables": variables,
            "connection_id": context.get("connection_id"),
        }
        result = Invoker.invoke_funct_on_aws_lambda(
            context,
            funct,
            params=params,
            aws_lambda=aws_lambda,
        )

        # Normalize GraphQL response to ensure consistent structure
        return Graphql.normalize_graphql_response(result)

    @staticmethod
    def fetch_graphql_schema(
        context,
        funct,
        aws_lambda=None,
    ):
        schema = Graphql.execute_graphql_query(
            context,
            funct,
            query=INTROSPECTION_QUERY,
            aws_lambda=aws_lambda,
        )

        if "__schema" in schema:
            return schema.get("__schema")

        return schema

    @staticmethod
    def extract_available_fields(schema, type_name):
        for type_def in schema["types"]:
            if type_def["name"] == type_name and type_def["kind"] == "OBJECT":
                return [
                    {
                        "name": field["name"],
                        "type": field["type"]["name"]
                        or (field["type"].get("ofType") or {}).get("name"),
                        "kind": field["type"]["kind"],
                    }
                    for field in type_def.get("fields", [])
                ]
        raise Exception(f"Type '{type_name}' not found in schema.")

    @staticmethod
    def generate_field_subselection(schema, type_name):
        try:
            fields = Graphql.extract_available_fields(schema, type_name)
            subselection = []
            for field in fields:
                if field["kind"] in ["OBJECT", "LIST"]:
                    if field["type"] and field["type"] not in [
                        "String",
                        "Int",
                        "Float",
                        "DateTime",
                        "JSON",
                    ]:
                        # Recursively generate subselection for nested objects
                        nested_fields = Graphql.generate_field_subselection(
                            schema, field["type"]
                        )
                        subselection.append(f"{field['name']} {{ {nested_fields} }}")
                    else:
                        subselection.append(field["name"])
                else:
                    subselection.append(field["name"])
            return " ".join(subselection)
        except Exception:
            return ""

    @staticmethod
    def normalize_graphql_response(response, operation_name=None):
        """
        Normalize GraphQL response to ensure consistent structure for test compatibility.

        Converts GraphQL error responses to have the expected data structure:
        - {"errors": [...]} -> {"data": {"askModel": None}, "errors": [...]}
        - {"errors": [...], "data": None} -> {"data": {"askModel": None}, "errors": [...]}

        Args:
            response: Raw GraphQL response dict
            operation_name: The GraphQL operation name to wrap (default: None)

        Returns:
            Normalized response dict with consistent structure
        """
        if not isinstance(response, dict):
            return response

        # If response has errors and no data key, add empty data structure
        if "errors" in response and "data" not in response:
            response["data"] = {operation_name: None}

        # If response has errors and data is None, ensure askModel structure exists
        elif "errors" in response and response.get("data") is None:
            response["data"] = {operation_name: None}

        # If response has data but the operation result is missing, ensure operation structure
        elif "data" in response and response["data"] is not None:
            if operation_name not in response["data"]:
                # Preserve existing data structure but add the missing operation
                existing_data = response["data"]
                response["data"] = {operation_name: None, **existing_data}

        return response

    @staticmethod
    def generate_graphql_operation(operation_name, operation_type, schema):
        def format_type(field_type):
            """Format the GraphQL type."""
            if field_type["kind"] == "NON_NULL":
                return f"{format_type(field_type['ofType'])}!"
            elif field_type["kind"] == "LIST":
                return f"[{format_type(field_type['ofType']) if field_type.get('ofType') else 'String'}]"
            return field_type["name"]

        def extract_operation_details(schema, operation_name, operation_type):
            """Extract operation details (query or mutation) from the schema."""
            for type_def in schema["types"]:
                if type_def["name"] == (
                    "Mutations" if operation_type == "Mutation" else operation_type
                ):
                    for field in type_def["fields"]:
                        if field["name"] == operation_name:
                            return field
            raise Exception(
                f"{operation_type.capitalize()} '{operation_name}' not found in the schema."
            )

        operation_details = extract_operation_details(
            schema, operation_name, operation_type
        )
        args = operation_details["args"]
        variable_definitions = ", ".join(
            f"${arg['name']}: {format_type(arg['type'])}" for arg in args
        )
        argument_usage = ", ".join(f"{arg['name']}: ${arg['name']}" for arg in args)

        return_type = operation_details["type"]
        if return_type["kind"] == "NON_NULL":
            return_type = return_type["ofType"]
        field_string = (
            Graphql.generate_field_subselection(schema, return_type["name"])
            if return_type["kind"] == "OBJECT"
            else ""
        )

        if not variable_definitions and not argument_usage and not field_string:
            return f"""{operation_type.lower()} {operation_name} {{{operation_name}}}"""
        return f"""
        {operation_type.lower()} {operation_name}({variable_definitions}) {{
            {operation_name}({argument_usage}) {{
                {field_string}
            }}
        }}
        """

    # @staticmethod
    # def extract_fields_from_ast(source, **kwargs):
    #     def extract_by_recursion(selections, **kwargs):
    #         fs = []
    #         dpt = kwargs.get("deepth")

    #         if type(dpt) is not int or dpt < 1:
    #             dpt = None
    #         else:

    #             dpt -= 1

    #         for s in selections:
    #             if not (s.name.value in fs):
    #                 fs.append(s.name.value.lower())

    #             if (
    #                 (dpt is None or dpt > 0)
    #                 and hasattr(s, "selection_set")
    #                 and type(s.selection_set) is SelectionSet
    #                 and type(s.selection_set.selections) is list
    #                 and len(s.selection_set.selections) > 0
    #             ):
    #                 fs += extract_by_recursion(s.selection_set.selections, deepth=dpt)

    #         return fs

    #     result = dict()
    #     operation = kwargs.get("operation")
    #     deepth = kwargs.get("deepth")
    #     ast = parse(source)

    #     for od in ast.definitions:
    #         on = od.operation.lower()

    #         if operation and on != operation.lower():
    #             continue

    #         result[on] = [od.name.value]

    #         if on in result:
    #             result[on] += extract_by_recursion(
    #                 od.selection_set.selections, deepth=deepth
    #             )
    #         else:
    #             result[on] = extract_by_recursion(
    #                 od.selection_set.selections, deepth=deepth
    #             )

    #     for operation in result:
    #         result[operation] = list({}.fromkeys(result[operation]).keys())

    #     return result

    # @staticmethod
    # def extract_flatten_ast(source):
    #     def extract_by_recursion(selections, path=""):
    #         fields = []

    #         if not path or path[-1] != "/":
    #             path += "/"

    #         for field in selections:
    #             if (
    #                 not hasattr(field, "name")
    #                 or field.name is None
    #                 or not hasattr(field.name, "value")
    #                 or not field.name.value
    #             ):
    #                 continue

    #             value = field.name.value.strip().lower()

    #             fields.append({"field": value, "path": path.strip().lower()})

    #             if (
    #                 hasattr(field, "selection_set")
    #                 and type(field.selection_set) is SelectionSet
    #                 and type(field.selection_set.selections) is list
    #                 and len(field.selection_set.selections) > 0
    #             ):
    #                 fields += extract_by_recursion(
    #                     field.selection_set.selections, path + value
    #                 )

    #         return fields

    #     def flatten(selections):
    #         output = {}

    #         for item in extract_by_recursion(selections):
    #             if output.get(item.get("path")) is None:
    #                 output[item.get("path")] = []

    #             if item.get("field") is not None and item.get("field") != "":
    #                 output[item.get("path")].append(item.get("field"))

    #         return output

    #     results = []
    #     ast = parse(source)

    #     if (
    #         ast
    #         and hasattr(ast, "definitions")
    #         and type(ast.definitions) is list
    #         and len(ast.definitions)
    #     ):
    #         for operation_definition in ast.definitions:
    #             result = {}

    #             if hasattr(operation_definition, "operation"):
    #                 result["operation"] = operation_definition.operation.strip().lower()

    #             if hasattr(operation_definition, "name") and hasattr(
    #                 operation_definition.name, "value"
    #             ):
    #                 result[
    #                     "operation_name"
    #                 ] = operation_definition.name.value.strip().lower()

    #             if (
    #                 hasattr(operation_definition, "selection_set")
    #                 and type(operation_definition.selection_set) is SelectionSet
    #                 and hasattr(operation_definition.selection_set, "selections")
    #                 and type(operation_definition.selection_set.selections) is list
    #                 and len(operation_definition.selection_set.selections) > 0
    #             ):
    #                 result["fields"] = flatten(
    #                     operation_definition.selection_set.selections
    #                 )

    #             results.append(result)

    #     return results


class JSON(graphene.Scalar):
    """
    The `JSON` scalar type represents JSON values as specified by
    [ECMA-404](http://www.ecma-international.org/
    publications/files/ECMA-ST/ECMA-404.pdf).
    """

    @staticmethod
    def identity(value):
        if isinstance(value, (str, bool, int, float)):
            return value.__class__(value)
        elif isinstance(value, (list, dict)):
            return value
        else:
            return None

    serialize = identity
    parse_value = identity

    @staticmethod
    def parse_literal(node):
        if isinstance(node, (ast.StringValue, ast.BooleanValue)):
            return node.value
        elif isinstance(node, ast.IntValue):
            return int(node.value)
        elif isinstance(node, ast.FloatValue):
            return float(node.value)
        elif isinstance(node, ast.ListValue):
            return [JSON.parse_literal(value) for value in node.values]
        elif isinstance(node, ast.ObjectValue):
            return {
                field.name.value: JSON.parse_literal(field.value)
                for field in node.fields
            }
        else:
            return None
