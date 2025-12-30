#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any

from .serializer import Serializer


class HttpResponse(object):
    @staticmethod
    def format_response(
        data: Any,
        status_code: int = 200,
        content_type: str = "application/json",
    ):
        content_type = (
            str(content_type).strip()
            if str(content_type).strip()
            else "application/json"
        )

        return {
            "statusCode": int(status_code),
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
                "Content-Type": content_type,
            },
            "body": Serializer.json_dumps(data),
        }
