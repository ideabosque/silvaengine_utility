#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bl"

import graphene
from graphql import parse
from graphql.language.ast import (
    SelectionSet,
    BooleanValue,
    StringValue,
    IntValue,
    ListValue,
    ObjectValue,
    FloatValue,
)


class Graphql(object):
    # Parse the graphql request's body to AST and extract fields from the AST
    @staticmethod
    def extract_fields_from_ast(source, **kwargs):
        def extract_by_recursion(selections, **kwargs):
            fs = []
            dpt = kwargs.get("deepth")

            if type(dpt) is not int or dpt < 1:
                dpt = None
            else:
                dpt -= 1

            for s in selections:
                if not (s.name.value in fs):
                    fs.append(s.name.value.lower())

                if (
                    (dpt is None or dpt > 0)
                    and hasattr(s, "selection_set")
                    and type(s.selection_set) is SelectionSet
                    and type(s.selection_set.selections) is list
                    and len(s.selection_set.selections) > 0
                ):
                    fs += extract_by_recursion(s.selection_set.selections, deepth=dpt)

            return fs

        result = dict()
        operation = kwargs.get("operation")
        deepth = kwargs.get("deepth")
        ast = parse(source)

        for od in ast.definitions:
            on = od.operation.lower()

            if operation and on != operation.lower():
                continue

            result[on] = [od.name.value]

            if on in result:
                result[on] += extract_by_recursion(
                    od.selection_set.selections, deepth=deepth
                )
            else:
                result[on] = extract_by_recursion(
                    od.selection_set.selections, deepth=deepth
                )

        for operation in result:
            result[operation] = list({}.fromkeys(result[operation]).keys())

        return result

    @staticmethod
    def extract_flatten_ast(source):
        def extract_by_recursion(selections, path=""):
            fields = []

            if not path or path[-1] != "/":
                path += "/"

            for field in selections:
                if (
                    field.name is None
                    or field.name.value is None
                    or field.name.value == ""
                ):
                    continue

                value = field.name.value.strip().lower()

                fields.append({"field": value, "path": path.strip().lower()})

                if (
                    hasattr(field, "selection_set")
                    and type(field.selection_set) is SelectionSet
                    and type(field.selection_set.selections) is list
                    and len(field.selection_set.selections) > 0
                ):
                    fields += extract_by_recursion(
                        field.selection_set.selections, path + value
                    )

            return fields

        def flatten(selections):
            output = {}

            for item in extract_by_recursion(selections):
                if output.get(item.get("path")) is None:
                    output[item.get("path")] = []

                if item.get("field") is not None and item.get("field") != "":
                    output[item.get("path")].append(item.get("field"))

            return output

        results = []
        ast = parse(source)

        if ast and type(ast.definitions) is list and len(ast.definitions):
            for operation_definition in ast.definitions:
                result = {}

                if operation_definition.operation:
                    result["operation"] = operation_definition.operation.strip().lower()

                if operation_definition.name and operation_definition.name.value:
                    result[
                        "operation_name"
                    ] = operation_definition.name.value.strip().lower()

                if (
                    hasattr(operation_definition, "selection_set")
                    and type(operation_definition.selection_set) is SelectionSet
                    and hasattr(operation_definition.selection_set, "selections")
                    and type(operation_definition.selection_set.selections) is list
                    and len(operation_definition.selection_set.selections) > 0
                ):
                    result["fields"] = flatten(
                        operation_definition.selection_set.selections
                    )

                results.append(result)

        return results


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
    def parse_literal(ast):
        if isinstance(ast, (StringValue, BooleanValue)):
            return ast.value
        elif isinstance(ast, IntValue):
            return int(ast.value)
        elif isinstance(ast, FloatValue):
            return float(ast.value)
        elif isinstance(ast, ListValue):
            return [JSON.parse_literal(value) for value in ast.values]
        elif isinstance(ast, ObjectValue):
            return {
                field.name.value: JSON.parse_literal(field.value)
                for field in ast.fields
            }
        else:
            return None
