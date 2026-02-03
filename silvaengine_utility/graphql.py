#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import functools
import logging
import threading
import time
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, Union

import boto3
import graphene
from graphene import Schema
from graphql import ExecutionResult, build_client_schema, get_introspection_query
from graphql.language import ast
from silvaengine_constants import HttpStatus, NamingConvention, OperationType

from .context import Context
from .debugger import Debugger
from .http import HttpResponse
from .invoker import Invoker
from .serializer import Serializer
from .utility import Utility


def graphql_service_initialization(func: Callable) -> Callable:
    """
    Decorator to intercept Graphql class initialization and queue settings data.

    This decorator intercepts the __init__ method of the Graphql class and
    sets the deployment mode in the Context for consumption by BaseModel subclasses.
    The queue operations are only enabled in production environment.

    Args:
        func: The __init__ method to decorate

    Returns:
        Wrapped function that sets deployment mode in context

    Usage:
        @graphql_service_initialization
        def __init__(self, logger, **setting):
            self.logger = logger
            self.setting = setting
    """

    @functools.wraps(func)
    def wrapper_function(
        self, logger: Optional[logging.Logger], **kwargs: Dict[str, Any]
    ) -> Any:
        try:
            if "regional_deployment" in kwargs:
                Context.set(
                    "regional_deployment",
                    kwargs.get("regional_deployment"),
                )

            if "endpoint_id" in kwargs:
                Context.set(
                    "endpoint_id",
                    str(kwargs.get("endpoint_id")).strip().lower(),
                )

            if logger and hasattr(logger, "info"):
                logger.info("Decorator `graphql_service_initialization` completed.")
            return func(self, logger, **kwargs)
        except Exception as e:
            if logger and hasattr(logger, "info"):
                logger.info(
                    f"Decorator `graphql_service_initialization` exception: {e}"
                )
            return func(self, logger, **kwargs)

    return wrapper_function


class Graphql(object):
    _graphql_schema_cache: Dict[str, Any] = {}
    _graphql_query_cache: Dict[str, str] = {}
    _lock: threading.RLock = threading.RLock()

    @graphql_service_initialization
    def __init__(
        self,
        logger: Optional[logging.Logger],
        **setting: Dict[str, Any],
    ) -> None:
        self.logger = logger
        self.setting = setting

    def execute(self, schema: Schema, **params: Dict[str, Any]) -> Any:
        if not isinstance(params, dict):
            raise ValueError("Invalid parameters")

        try:
            context = {
                "logger": self.logger,
                "setting": self.setting,
                "aws_api_key": params.get("api_key"),
                "aws_api_stage": params.get("stage"),
                "aws_api_area": params.get("area"),
                "endpoint_id": params.get("endpoint_id"),
                "connection_id": params.get("connection_id"),
                "aws_lambda_arn": params.get("aws_lambda_arn"),
            }

            if isinstance(params.get("metadata"), dict):
                context.update(**params.get("metadata", {}))

            if isinstance(params.get("context"), dict):
                context.update(**params.get("context", {}))

            query = params.get("query")

            if not query:
                return Graphql.error_response(errors="Invalid operations")

            execution_result = Invoker.sync_call_async_compatible(
                coroutine_task=schema.execute_async(
                    query,
                    context_value=context,
                    variable_values=params.get("variables", {}),
                    operation_name=params.get("operation_name"),
                )
            )

            if execution_result:
                # Check for errors first - GraphQL can have both data and errors
                if execution_result.errors:
                    Debugger.info(
                        variable=f"Query: {query}, Variables: {params.get('variables', {})}, Errors: {execution_result.errors}",
                        stage="Graphql Debug(execute result)",
                        setting=self.setting,
                    )
                    return Graphql.error_response(
                        errors=[
                            Utility.format_error(e) for e in execution_result.errors
                        ],
                        status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
                    )
                elif execution_result.data:
                    return Graphql.success_response(data=execution_result.data)

            return Graphql.error_response(
                errors="Invalid execution result",
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
            )
        except Exception as e:
            Debugger.info(
                variable=e,
                stage="Graphql Debug(execute)",
                setting=self.setting,
            )
            return Graphql.error_response(
                errors=str(e),
                status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
            )

    @staticmethod
    def build_graphql_schema() -> Schema:
        raise NotImplementedError("Subclasses must implement the handle method.")

    @staticmethod
    def success_response(data: Any) -> dict[str, Any]:
        return HttpResponse.format_response({"data": data})

    @staticmethod
    def error_response(
        errors: Union[str, list],
        status_code: int = HttpStatus.INTERNAL_SERVER_ERROR.value,
    ) -> dict[str, Any]:
        return HttpResponse.format_response({"errors": errors}, status_code)

    # TODO: Will be deprecated
    @staticmethod
    def execute_graphql_query(
        context: dict[str, Any],
        funct: str,
        query: str,
        variables: dict[str, Any] = {},
        aws_lambda: boto3.client = None,
    ) -> dict[str, Any]:
        # exclude = ["logger", "setting"]

        # for k in exclude:
        #     context.pop(k)

        result = Invoker.invoke_funct_on_aws_lambda(
            context,
            funct,
            params={
                "query": query,
                "variables": variables,
                **context,
            },
            aws_lambda=aws_lambda,
        )

        # Normalize GraphQL response to ensure consistent structure
        return Graphql.normalize_graphql_response(result)

    # TODO: Will be deprecated
    @staticmethod
    def fetch_graphql_schema(
        context: dict[str, Any],
        funct: str,
        aws_lambda: boto3.client = None,
    ) -> dict[str, Any]:
        schema = Graphql.execute_graphql_query(
            context,
            funct,
            query=get_introspection_query(),
            aws_lambda=aws_lambda,
        )

        if isinstance(schema, dict):
            if "data" in schema:
                schema = schema.get("data")

            if isinstance(schema, dict) and "__schema" in schema:
                return schema.get("__schema", {})

        return schema if schema is not None else {}

    @staticmethod
    def request_graphql(
        context: dict[str, Any],
        module_name: str,
        function_name: str,
        operation_name: str,
        operation_type: str = OperationType.QUERY.value,
        query: Optional[str] = None,
        class_name: Optional[str] = None,
        variables: Optional[dict[str, Any]] = None,
        enable_preferred_custom_query: bool = True,
    ) -> dict[str, Any]:
        if not all(
            [
                module_name,
                function_name,
                context,
                operation_name,
            ]
        ):
            raise ValueError("Missing required parameter(s)")

        if "setting" not in context:
            raise ValueError("Missing `setting` in context")

        execution_context = context.copy()
        query = query if isinstance(query, str) and str(query).strip() else ""
        module_name = str(module_name).strip()
        function_name = str(function_name).strip()
        operation_name = str(operation_name).strip()
        operation_type = OperationType.get(operation_type).value
        settings = execution_context.pop("setting", {})
        logger = execution_context.pop("logger", logging.getLogger(module_name))
        constructor_parameters = {"logger": logger, **settings}
        proxied_agent = Invoker.resolve_proxied_callable(
            module_name=module_name,
            class_name=class_name,
            constructor_parameters=constructor_parameters,
        )
        call_chain = f"{operation_type} {operation_name}({module_name}.{class_name}.{function_name})"

        if not query:
            schema_picker = execution_context.get("graphql_schema_picker")

            if schema_picker and callable(schema_picker):
                query = schema_picker(
                    operation_type=operation_type,
                    operation_name=operation_name,
                    module_name=module_name,
                    enable_preferred_custom_schema=enable_preferred_custom_query,
                )

                Debugger.info(
                    variable=f"Fetch schema from database: {call_chain}, query: {query}",
                    stage=f"{__file__}.request_graphql.schema_picker",
                    setting=settings,
                )

        if not query:
            Debugger.info(
                variable=f"Introspection query `{call_chain}`",
                stage=f"{__file__}.request_graphql.introspection",
                setting=settings,
                delimiter="#",
            )

            schema_cache_index = f"{module_name}_{class_name or 'default'}".lower()
            schema = Graphql._graphql_schema_cache.get(schema_cache_index)

            if not schema:
                schema_function = getattr(proxied_agent, "build_graphql_schema", None)

                if not schema_function or not callable(schema_function):
                    raise ValueError(
                        f"`{module_name}.{class_name}.build_graphql_schema` is not exists"
                    )

                schema_object = schema_function()

                if not isinstance(schema_object, Schema):
                    raise ValueError("Invalid schema")

                result = schema_object.execute(get_introspection_query())

                if result.errors:
                    raise ValueError(f"Introspection query error: {result.errors}")

                schema = result.data if result.data is not None else {}

                if isinstance(schema, dict) and "__schema" in schema:
                    schema = schema["__schema"]

                with Graphql._lock:
                    Graphql._graphql_schema_cache[schema_cache_index] = schema

            query_cache_index = f"{operation_type}_{operation_name}".lower()
            query = Graphql._graphql_query_cache.get(query_cache_index)

            if not query:
                query = Graphql.generate_graphql_operation(
                    operation_name=operation_name,
                    operation_type=operation_type,
                    schema=schema,
                )

                with Graphql._lock:
                    Graphql._graphql_query_cache[query_cache_index] = query

        proxied_function = getattr(proxied_agent, function_name, None)

        if not proxied_function or not callable(proxied_function):
            raise ValueError(
                f"`{module_name}.{class_name}.{proxied_function}` is not exists or uncallable"
            )

        result = proxied_function(
            **{
                "query": query,
                "variables": variables,
                "context": execution_context,
            }
        )

        if (
            not isinstance(result, dict)
            or "statusCode" not in result
            or "body" not in result
        ):
            raise ValueError(f"Invalid response structure: {result}")

        status_code = str(result.get("statusCode")).strip()
        result_body = result.get("body")

        if not result_body:
            return {}

        if isinstance(result_body, (str, bytes)):
            result_body = Serializer.json_loads(result_body)

        if status_code.startswith("20"):
            return result_body.get("data", {}).get(operation_name, {})
        elif "errors" in result_body:
            raise ValueError(f"Request graphql error: {result_body.get('errors')}")
        else:
            raise ValueError(f"Request graphql error with status: {status_code}")

    @staticmethod
    def get_graphql_schema(
        module_name: str,
        class_name: str | None = None,
    ) -> dict[str, Any]:
        cache_index = f"{module_name}_{str(class_name).strip() or 'default'}".lower()
        schema = Graphql._graphql_schema_cache.get(cache_index)

        if schema:
            return schema

        result = Graphql._get_graphql_schema(
            module_name=module_name,
            class_name=class_name,
        )

        if not result:
            raise ValueError("Invalid schema introspection")
        elif result.errors:
            raise ValueError(f"Introspection query error: {result.errors}")

        schema = result.data if result.data is not None else {}

        if isinstance(schema, dict) and "__schema" in schema:
            schema = schema["__schema"]

        with Graphql._lock:
            Graphql._graphql_schema_cache[cache_index] = schema

        return schema

    @staticmethod
    def get_schema_root_fields(
        module_name: str,
        class_name: Optional[str] = None,
        types: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict]]:
        result = Graphql._get_graphql_schema(
            module_name=module_name,
            class_name=class_name,
        )

        if result.errors:
            raise ValueError(f"Failed to query introspection: {result.errors}")
        elif not hasattr(result, "data"):
            raise ValueError("Invalid introspection result")

        client_schema = build_client_schema(introspection=result.data)

        if not types or len(types) < 1:
            types = ["Query", "Mutation", "Subscription"]

        fields: Dict[str, List[Dict]] = {t: [] for t in types}

        for operation in types:
            meta = getattr(client_schema, f"{operation.lower()}_type", None)

            if not meta:
                continue

            for field in getattr(meta, "fields", []):
                fields[operation].append(field)

        return fields

    @staticmethod
    def _get_graphql_schema(
        module_name: str,
        class_name: Optional[str] = None,
    ) -> ExecutionResult:
        module_name = module_name.strip()

        if not module_name:
            raise ValueError("Missing required parameter(s)")

        schema_scanner = Invoker.resolve_proxied_callable(
            module_name=module_name,
            class_name=class_name,
            function_name="build_graphql_schema",
        )()

        return schema_scanner.execute(get_introspection_query())

    @staticmethod
    def extract_available_fields(
        schema: dict[str, Any], type_name: str
    ) -> list[dict[str, Any]]:
        for type_def in schema["types"]:
            if type_def["name"] == type_name and type_def["kind"] == "OBJECT":
                return [
                    Graphql.get_real_field_data(field)
                    for field in type_def.get("fields", [])
                ]
        raise Exception(f"Type '{type_name}' not found in schema.")

    @staticmethod
    def get_real_field_data(field: dict[str, Any]) -> dict[str, Any]:
        if field["name"] == "edges":
            return {
                "name": field["name"],
                "type": (field["type"].get("ofType") or {})
                .get("ofType", {})
                .get("name"),
                "kind": (field["type"].get("ofType") or {})
                .get("ofType", {})
                .get("kind"),
            }
        if field["name"] == "pageInfo":
            return {
                "name": field["name"],
                "type": (field["type"].get("ofType") or {}).get("name"),
                "kind": (field["type"].get("ofType") or {}).get("kind"),
            }
        return {
            "name": field["name"],
            "type": field["type"]["name"]
            or (field["type"].get("ofType") or {}).get("name"),
            "kind": field["type"]["kind"],
        }

    @staticmethod
    def generate_field_subselection(schema: dict[str, Any], type_name: str) -> str:
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
                        "JSONCamelCase",
                        "JSONSnakeCase",
                        "SafeFloat",
                    ]:
                        # Recursively generate subselection for nested objects
                        nested_fields = Graphql.generate_field_subselection(
                            schema, field["type"]
                        )
                        subselection.append(f"{field['name']} {{ {nested_fields}}}")
                    else:
                        subselection.append(field["name"])
                else:
                    subselection.append(field["name"])
            return " ".join(subselection)
        except Exception:
            return ""

    @staticmethod
    def normalize_graphql_response(
        response: Any, operation_name: Optional[str] = None
    ) -> dict[str, Any]:
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
    def generate_graphql_operation(
        operation_name: str,
        operation_type: str,
        schema: dict[str, Any],
    ) -> str:
        if not all([operation_name, operation_type]):
            raise ValueError("Invalid arguments")

        operation_name = operation_name.strip()
        operation_type = operation_type.strip()
        cache_index = f"{operation_type.lower()}_{operation_name.lower()}"
        query = Graphql._graphql_query_cache.get(cache_index)

        if query:
            return query

        def format_type(field_type: dict[str, Any]) -> str:
            """Format the GraphQL type."""
            if field_type["kind"] == "NON_NULL":
                return f"{format_type(field_type['ofType'])}!"
            elif field_type["kind"] == "LIST":
                return f"[{format_type(field_type['ofType']) if field_type.get('ofType') else 'String'}]"
            return field_type["name"]

        def extract_operation_details(
            schema: dict[str, Any], operation_name: str, operation_type: str
        ) -> dict[str, Any]:
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

        with Graphql._lock:
            if not variable_definitions and not argument_usage and not field_string:
                Graphql._graphql_query_cache[cache_index] = (
                    f"""{operation_type.lower()} {operation_name} {{{operation_name}}}"""
                )
                return Graphql._graphql_query_cache.get(cache_index)

            Graphql._graphql_query_cache[cache_index] = f"""
            {operation_type.lower()} {operation_name}({variable_definitions}) {{
                {operation_name}({argument_usage}) {{
                    {field_string}
                }}
            }}
            """

            return Graphql._graphql_query_cache.get(cache_index)


class JSON(graphene.Scalar):
    """
    JSON scalar type for GraphQL with dynamic key style support.

    The `JSON` scalar type represents JSON values as specified by
    [ECMA-404](http://www.ecma-international.org/publications/files/ECMA-ST/ECMA-404.pdf).

    Extended features:
    - Dynamic key_style switching between camelCase and snake_case
    - Automatic key conversion during serialization and parsing
    - Recursive key conversion for nested structures
    - Type safety with proper validation

    Attributes:
        _key_style: Current key style (NamingConvention.CAMEL or NamingConvention.SNAKE)
    """

    _key_style: NamingConvention = NamingConvention.CAMEL

    @classmethod
    def camel_case(cls) -> "JSON":
        """Create a JSON scalar instance with camelCase key style.

        Returns:
            JSON scalar instance configured for camelCase output
        """
        instance = cls()
        instance._key_style = NamingConvention.CAMEL
        return instance

    @classmethod
    def snake_case(cls) -> "JSON":
        """Create a JSON scalar instance with snake_case key style.

        Returns:
            JSON scalar instance configured for snake_case output
        """
        instance = cls()
        instance._key_style = NamingConvention.SNAKE
        return instance

    @staticmethod
    def transform_dict_keys(
        data: Any,
        key_style: NamingConvention = NamingConvention.CAMEL,
    ) -> Any:
        """Recursively convert all keys in JSON data to specified naming style.

        Args:
            data: Input data (dict, list, or primitive type)
            key_style: Target naming style - NamingConvention.CAMEL or NamingConvention.SNAKE

        Returns:
            Data with all keys converted to specified style
        """
        if isinstance(data, (str, bool, int, float, type(None))):
            return data
        elif isinstance(data, list):
            return [JSON.transform_dict_keys(item, key_style) for item in data]
        elif isinstance(data, dict):
            result = {}
            convert_func = (
                Utility.to_camel_case
                if key_style == NamingConvention.CAMEL
                else Utility.to_snake_case
            )
            for k, v in data.items():
                key = convert_func(str(k)).strip() if isinstance(k, str) else k
                result[key] = JSON.transform_dict_keys(v, key_style)
            return result
        else:
            return str(data)

    @staticmethod
    def identity(value: Any) -> Any:
        """Return value unchanged for serialization.

        Args:
            value: Input value

        Returns:
            The same value if it's a valid JSON type, None otherwise
        """
        if isinstance(value, (str, bool, int, float)):
            return value.__class__(value)
        elif isinstance(value, (list, dict)):
            return value
        elif isinstance(value, Decimal):
            return float(value)
        else:
            return None

    def _get_reversed_key_style(self) -> NamingConvention:
        if self._key_style == NamingConvention.CAMEL:
            return NamingConvention.SNAKE
        return NamingConvention.CAMEL

    def serialize(self, value: Any) -> Any:
        """Serialize value to JSON with key style conversion.

        Args:
            value: Input value to serialize

        Returns:
            JSON value with keys converted to configured style
        """
        raw_value = JSON.identity(value)
        return self.transform_dict_keys(raw_value, self._key_style)

    def parse_value(self, value: Any) -> Any:
        """Parse value from JSON with reverse key style conversion.

        Args:
            value: Input value to parse

        Returns:
            Parsed value with keys converted from configured style
        """
        raw_value = JSON.identity(value)
        return self.transform_dict_keys(raw_value, self._get_reversed_key_style())

    @staticmethod
    def parse_literal(node: ast.Node) -> Any:
        """Parse GraphQL AST literal node to Python value.

        Args:
            node: GraphQL AST node

        Returns:
            Python value corresponding to AST node
        """
        if isinstance(node, ast.StringValue):
            return node.value
        elif isinstance(node, ast.BooleanValue):
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


class JSONCamelCase(JSON):
    """JSON scalar with `camelCase` key style."""

    _key_style: NamingConvention = NamingConvention.CAMEL

    @staticmethod
    def identity(value: Any) -> Any:
        return JSON.identity(value)

    @staticmethod
    def serialize(value: Any) -> Any:
        raw_value = JSON.identity(value)
        return JSON.transform_dict_keys(raw_value, NamingConvention.CAMEL)

    @staticmethod
    def parse_value(value: Any) -> Any:
        raw_value = JSON.identity(value)
        return JSON.transform_dict_keys(raw_value, NamingConvention.SNAKE)

    @staticmethod
    def parse_literal(node: ast.Node) -> Any:
        return JSON.parse_literal(node)


class JSONSnakeCase(JSON):
    """JSON scalar with `snake_case` key style."""

    _key_style: NamingConvention = NamingConvention.SNAKE

    @staticmethod
    def identity(value: Any) -> Any:
        return JSON.identity(value)

    @staticmethod
    def serialize(value: Any) -> Any:
        raw_value = JSON.identity(value)
        return JSON.transform_dict_keys(raw_value, NamingConvention.SNAKE)

    @staticmethod
    def parse_value(value: Any) -> Any:
        raw_value = JSON.identity(value)
        return JSON.transform_dict_keys(raw_value, NamingConvention.CAMEL)

    @staticmethod
    def parse_literal(node: ast.Node) -> Any:
        return JSON.parse_literal(node)


class SafeFloat(graphene.Scalar):
    """Custom Float Scalar with automatic conversion from Decimal to float"""

    @staticmethod
    def serialize(value):
        if isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, (int, float)):
            return float(value)
        raise ValueError(f"Invalid Float value: {value}")

    @staticmethod
    def parse_literal(node):
        if isinstance(node, ast.FloatValue):
            return float(node.value)
        if isinstance(node, ast.IntValue):
            return float(node.value)
        raise ValueError(f"Invalid Float literal: {node}")

    @staticmethod
    def parse_value(value):
        if isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, (int, float)):
            return float(value)
        raise ValueError(f"Invalid Float value: {value}")
