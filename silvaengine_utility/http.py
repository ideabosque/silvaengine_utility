#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bl"

from graphql.error import GraphQLError, format_error as format_graphql_error
from .utility import Utility


class HttpResponse(object):
    @staticmethod
    def response_json(status_code, data):
        body = {}

        if status_code and str(status_code)[0] == "2":
            body["data"] = data
        elif isinstance(data, GraphQLError):
            body["errors"] = format_graphql_error(data)
        else:
            body["message"] = str(data)

        return {
            "statusCode": int(status_code),
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
            },
            "body": (
                Utility.json_dumps(
                    body,
                    indent=4,
                )
            ),
        }
