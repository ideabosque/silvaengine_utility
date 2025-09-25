#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bl"

try:
    from graphql.error import GraphQLError, format_error as format_graphql_error
except ImportError:  # pragma: no cover - graphql-core>=3.2 removed format_error
    from graphql import GraphQLError

    def format_graphql_error(error):
        return getattr(error, "formatted", {"message": str(error)})

from .utility import Utility


class HttpResponse(object):
    @staticmethod
    def response_json(status_code, data):
        body = {}
        status_code = int(status_code) if status_code else 500

        if status_code and str(status_code)[0] == "2":
            body["data"] = data

            if data is None:
                status_code = 406
        elif isinstance(data, GraphQLError):
            body["errors"] = format_graphql_error(data)
        else:
            body["message"] = str(data) if data else "Unkown"

        return {
            "statusCode": int(status_code),
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
            },
            "body": (Utility.json_dumps(body)),
        }
