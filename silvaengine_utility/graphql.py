#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import asyncio
import functools
import logging
from typing import Any, Callable, Dict, Optional, Union

import boto3
import graphene
from graphene import Schema
from graphql import parse
from graphql.language import ast

from .context import Context
from .http import HttpResponse
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
                    "endpoint_id", str(kwargs.get("endpoint_id")).strip().lower()
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
    # Parse the graphql request's body to AST and extract fields from the AST
    @graphql_service_initialization
    def __init__(self, logger: Optional[logging.Logger], **setting: Any) -> None:
        self.logger = logger
        self.setting = setting

    def execute(self, schema: Schema, **params: Dict[str, Any]) -> Any:
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

            result = schema.execute_async(
                query,
                context_value=context,
                variable_values=params.get("variables", {}),
                operation_name=params.get("operation_name"),
            )

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self.logger.info(f"Execute Graphql (run) {'>' * 40}")
                execution_result = asyncio.run(result)
                self.logger.info(f"Execute Graphql (run) {'>' * 40} {execution_result}")
            else:
                self.logger.info(
                    f"Execute Graphql (run_coroutine_threadsafe) {'>' * 40}"
                )
                execution_result = asyncio.run_coroutine_threadsafe(
                    result, loop
                ).result()

                self.logger.info(
                    f"Execute Graphql (run_coroutine_threadsafe) {'>' * 40} {execution_result}"
                )

            if execution_result:
                if execution_result.data:
                    return Graphql.success_response(execution_result.data)
                elif execution_result.errors:
                    return Graphql.error_response(
                        [Utility.format_error(e) for e in execution_result.errors], 500
                    )

            return Graphql.error_response("Uncaught execution error.", 500)
        except Exception as e:
            return Graphql.error_response(str(e), 500)

    @staticmethod
    def success_response(data: Any) -> dict[str, Any]:
        return HttpResponse.format_response({"data": data})

    @staticmethod
    def error_response(
        errors: Union[str, list], status_code: int = 400
    ) -> dict[str, Any]:
        return HttpResponse.format_response({"errors": errors}, status_code)

    @staticmethod
    def execute_graphql_query(
        context: dict[str, Any],
        funct: str,
        query: str,
        variables: dict[str, Any] = {},
        aws_lambda: boto3.client = None,
    ) -> dict[str, Any]:
        params = {
            "query": query,
            "variables": variables,
            **context,
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
        context: dict[str, Any],
        funct: str,
        aws_lambda: boto3.client = None,
    ) -> dict[str, Any]:
        schema = Graphql.execute_graphql_query(
            context,
            funct,
            query=INTROSPECTION_QUERY,
            aws_lambda=aws_lambda,
        )

        if schema and type(schema) is dict:
            if "data" in schema:
                schema = schema.get("data")

            if "__schema" in schema:
                return schema.get("__schema")

        return schema if schema is not None else {}

    @staticmethod
    def extract_available_fields(
        schema: dict[str, Any], type_name: str
    ) -> list[dict[str, Any]]:
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
        operation_name: str, operation_type: str, schema: dict[str, Any]
    ) -> str:
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

        if not variable_definitions and not argument_usage and not field_string:
            return f"""{operation_type.lower()} {operation_name} {{{operation_name}}}"""

        return f"""
        {operation_type.lower()} {operation_name}({variable_definitions}) {{
            {operation_name}({argument_usage}) {{
                {field_string}
            }}
        }}
        """


class JSON(graphene.Scalar):
    """
    The `JSON` scalar type represents JSON values as specified by
    [ECMA-404](http://www.ecma-international.org/
    publications/files/ECMA-ST/ECMA-404.pdf).
    """

    @staticmethod
    def identity(value: Any) -> Any:
        if isinstance(value, (str, bool, int, float)):
            return value.__class__(value)
        elif isinstance(value, (list, dict)):
            return value
        else:
            return None

    serialize = identity
    parse_value = identity

    @staticmethod
    def parse_literal(node: ast.Node) -> Any:
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
