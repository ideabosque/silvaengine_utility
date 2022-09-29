#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from types import FunctionType
from importlib.util import find_spec
from importlib import import_module
from decimal import Decimal
from datetime import datetime, date
from graphql.error import GraphQLError, format_error as format_graphql_error
from sqlalchemy import create_engine, orm, inspect
from sqlalchemy.ext.declarative import DeclarativeMeta
import json, dateutil, re, struct, socket, asyncio

# import jsonpickle
# from sqlalchemy.ext.declarative import DeclarativeMeta

__author__ = "bibow"


datetime_format = "%Y-%m-%dT%H:%M:%S%z"
datetime_format_regex_patterns = [
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+|-]\d{4}$",
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+|-]\d{2}:\d{2}$",
]


class JSONEncoder(json.JSONEncoder):
    def default(self, o):  # pylint: disable=E0202
        if isinstance(o.__class__, DeclarativeMeta):

            def convert_object_to_dict(obj, found=None):
                if found is None:
                    found = set()

                mapper = orm.class_mapper(obj.__class__)
                columns = [column.key for column in mapper.columns]
                get_key_value = (
                    lambda c: (c, getattr(obj, c).isoformat())
                    if isinstance(getattr(obj, c), datetime)
                    else (c, getattr(obj, c))
                )
                out = dict(map(get_key_value, columns))

                for name, relation in mapper.relationships.items():
                    if relation not in found:
                        found.add(relation)
                        related_obj = getattr(obj, name)

                        if related_obj is not None:
                            out[name] = (
                                [
                                    convert_object_to_dict(child, found)
                                    for child in related_obj
                                ]
                                if relation.uselist
                                else convert_object_to_dict(related_obj, found)
                            )
                return out

            return convert_object_to_dict(o)
        elif isinstance(o, Decimal):
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
                for datetime_format_regex_pattern in datetime_format_regex_patterns:
                    datetime_format_regex = re.compile(datetime_format_regex_pattern)
                    if datetime_format_regex.match(value):
                        o[key] = dateutil.parser.parse(value)
                        break
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
        # return jsonpickle.encode(data, unpicklable=False)

    @staticmethod
    def json_loads(data, parser_number=True):
        if parser_number:
            return json.loads(
                data, cls=JSONDecoder, parse_float=Decimal, parse_int=Decimal
            )
        return json.loads(data, cls=JSONDecoder)
        # return jsonpickle.decode(data)

    # Check the specified ip exists in the given ip segment
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
    def is_static_method(callable_method):
        return callable(callable_method) and type(callable_method) is FunctionType

    # Import the module dynamically
    @staticmethod
    def import_dynamically(
        module_name, function_name, class_name=None, constructor_parameters=None
    ):
        if not module_name or not function_name:
            return None

        module_name = str(module_name).strip()
        function_name = str(function_name).strip()

        # 1. Load module by dynamic
        spec = find_spec(name=module_name, package=module_name)

        if spec is None:
            return None

        agent = import_module(name=module_name, package=module_name)
        # agent = __import__("{}.{}".format(module_name, module_name))

        if not agent:
            return None

        if class_name and hasattr(agent, str(class_name).strip()):
            class_name = str(class_name).strip()

            if type(constructor_parameters) is dict and len(
                constructor_parameters.keys()
            ):
                agent = getattr(agent, class_name)(**constructor_parameters)
            elif Utility.is_static_method(
                getattr(getattr(agent, class_name), function_name)
            ):
                agent = getattr(agent, class_name)
            else:
                try:
                    agent = getattr(agent, class_name)()
                except:
                    return None

        if not hasattr(agent, function_name):
            return None

        return getattr(agent, function_name)

    # Call function by async
    @staticmethod
    def call_by_async(callable):
        try:

            async def exec_async_functions(callable):
                if type(callable) is list and len(callable):
                    print("Execute functions by async")
                    tasks = []

                    for fn in callable:
                        if hasattr(fn, "__call__"):
                            tasks.append(fn)

                    await asyncio.gather(*tasks)
                elif hasattr(callable, "__call__"):
                    print("Execute function by async")
                    await asyncio.gather(callable())

            return asyncio.run(exec_async_functions(callable))
        except Exception as e:
            raise e

    @staticmethod
    def create_database_session(settings):
        try:
            assert type(settings) is dict and len(
                settings
            ), "Missing configuration items required to connect to mysql database."

            required_settings = ["user", "password", "host", "port", "schema"]

            for key in required_settings:
                assert settings.get(
                    key
                ), f"Missing required configuration item `{key}`."

            dsn = "{}+{}://{}:{}@{}:{}/{}?charset={}".format(
                settings.get("type", "mysql"),
                settings.get("driver", "pymysql"),
                settings.get("user"),
                settings.get("password", ""),
                settings.get("host"),
                settings.get("port", 3306),
                settings.get("schema"),
                settings.get("charset", "utf8mb4"),
            )

            return orm.scoped_session(
                orm.sessionmaker(
                    autocommit=False, 
                    autoflush=False, 
                    bind=create_engine(
                        dsn,
                        pool_size=settings.get("pool_size", 10),
                        max_overflow=settings.get("max_overflow", -1),
                        pool_recycle=settings.get("pool_size", 1200),
                    ),
                )
            )
        except Exception as e:
            raise e

    # Convert camel case to underscore
    @staticmethod
    def convert_camel_to_underscore(text, separator="_"):
        if not separator:
            separator = "_"

        return "".join(
            [
                char if not char.isupper() or index == 0 else f"{separator}{char}"
                for index, char in enumerate(text)
            ]
        ).lower()

    @staticmethod
    def is_json_string(string):
        try:
            json.loads(string)
            return True
        except:
            return False

    @staticmethod
    def convert_object_to_dict(instance):
        # return {
        #     c.key: getattr(instance, c.key)
        #     for c in inspect(instance).mapper.column_attrs
        # }
        attributes = {}

        for attribute in dir(instance):
            attribute = str(attribute).strip()
            value = getattr(instance, attribute)

            if not str(attribute).strip().startswith("__") and not callable(value):
                attributes[attribute] = value

        return attributes
