#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any

from silvaengine_constants import HttpStatus

from .serializer import Serializer


class HttpResponse(object):
    @staticmethod
    def format_response(
        data: Any,
        status_code: int = HttpStatus.OK.value,
        content_type: str = "application/json",
        as_websocket_format: bool = False,
    ):
        content_type = (
            str(content_type).strip()
            if str(content_type).strip()
            else "application/json"
        )

        response = {
            "statusCode": int(status_code),
            "body": Serializer.json_dumps(data),
        }

        if not as_websocket_format:
            response.update(
                headers={
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": content_type,
                }
            )

        return response
