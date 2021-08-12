#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import json, dateutil, re, struct, socket
from importlib.util import find_spec
from importlib import import_module
from decimal import Decimal
from datetime import datetime, date
from graphql.error import GraphQLError, format_error as format_graphql_error

datetime_format = "%Y-%m-%dT%H:%M:%S"
datetime_format_regex = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class JSONEncoder(json.JSONEncoder):
    def default(self, o):  # pylint: disable=E0202
        if isinstance(o, Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        elif hasattr(o, "attribute_values"):
            return o.attribute_values
        elif isinstance(o, (datetime, date)):
            return o.strftime(datetime_format)
        elif isinstance(o, (bytes, bytearray)):
            return str(o)
        elif hasattr(o, "__dict__"):
            return o.__dict__
        else:
            return super(JSONEncoder, self).default(o)


class JSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, o):  # pylint: disable=E0202
        if o.get("_type") in ["bytes", "bytearray"]:
            return str(o["value"])

        for (key, value) in o.items():
            try:
                if not isinstance(value, str):
                    continue
                if datetime_format_regex.match(value):
                    o[key] = dateutil.parser.parse(value)
            except (ValueError, AttributeError):
                pass

        return o


class Struct(object):
    def __init__(self, **d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
                setattr(self, a, [Struct(**x) if isinstance(x, dict) else x for x in b])
            else:
                setattr(self, a, Struct(**b) if isinstance(b, dict) else b)


class Utility(object):
    @staticmethod
    def format_error(error):
        if isinstance(error, GraphQLError):
            return format_graphql_error(error)

        return {"message": str(error)}

    @staticmethod
    def json_dumps(data):
        return json.dumps(
            data,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
            cls=JSONEncoder,
            ensure_ascii=False,
        )

    @staticmethod
    def json_loads(data, parser_number=True):
        if parser_number:
            return json.loads(
                data, cls=JSONDecoder, parse_float=Decimal, parse_int=Decimal
            )
        return json.loads(data, cls=JSONDecoder)

    @staticmethod
    def in_subnet(ip, subnet) -> bool:
        if type(subnet) is str and str:
            match = re.match("(.*)/(.*)", subnet)

            if match:
                subnet = match.group(1)
                shift = int(match.group(2))
                nip = struct.unpack("I", socket.inet_aton(str(ip)))[0]
                nsubnet = struct.unpack("I", socket.inet_aton(subnet))[0]
                mask = (1 << shift) - 1

                return (nip & mask) == (nsubnet & mask)

            return str(ip).strip() == subnet.strip()
        elif type(subnet) is list and len(subnet):
            return str(ip) in [str(value).strip() for value in subnet]

        return str(ip).strip() == str(subnet).strip()

    @staticmethod
    def import_dynamically(
        module_name, function_name, class_name=None, constructor_parameters=None
    ):
        if not module_name or not function_name:
            return None

        # 1. Load module by dynamic
        spec = find_spec(module_name)

        if spec is None:
            return None

        agent = import_module(module_name)

        if hasattr(agent, class_name):
            if type(constructor_parameters) is dict and len(
                constructor_parameters.keys()
            ):
                agent = getattr(agent, class_name)(**constructor_parameters)
            else:
                agent = getattr(agent, class_name)()

        if not hasattr(agent, function_name):
            return None

        return getattr(agent, function_name)
