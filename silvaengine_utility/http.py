#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict, Optional

from silvaengine_constants import HttpStatus

from .serializer import Serializer


class HttpResponse(object):
    @staticmethod
    def format_response(
        data: Any,
        status_code: int = HttpStatus.OK.value,
        headers: Optional[Dict[str, Any]] = None,
        content_type: str = "application/json",
    ):
        content_type = (
            str(content_type).strip()
            if str(content_type).strip()
            else "application/json"
        )

        response_headers = {
            "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
            "Access-Control-Allow-Origin": "*",
            "Content-Type": content_type,
        }

        if isinstance(headers, dict):
            response_headers.update(headers)

        return {
            "statusCode": int(status_code),
            "headers": response_headers,
            "body": Serializer.json_dumps(data),
        }
