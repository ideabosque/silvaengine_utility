#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import functools
import logging
from typing import Any, Callable, Optional

import graphene
from graphql import parse
from graphql.language import ast

from .context import Context
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
        self: Any,
        logger: Optional[logging.Logger],
        **kwargs: Any,
    ) -> Any:
        try:
            logger.info("*" * 100)
            logger.info(kwargs)
            logger.info("*" * 100)
            if "regional_deployment" in kwargs:
                Context.set(
                    "regional_deployment",
                    kwargs.get("regional_deployment"),
                )

            if "endpoint_id" in kwargs:
                Context.set(
                    "endpoint_id", str(kwargs.get("endpoint_id")).strip().lower()
                )

            logger.info(f"Decorator `graphql_service_initialization` completed.")
            return func(self, logger, **kwargs)
        except Exception as e:
            logger.info(f"Decorator `graphql_service_initialization` exception: {e}")
            return func(self, logger, **kwargs)

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
