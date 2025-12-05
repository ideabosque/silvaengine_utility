#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import asyncio
import json
import re
import socket
import struct
import traceback
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from importlib.util import find_spec
from types import FunctionType

import dateutil
from sqlalchemy import create_engine, orm
from sqlalchemy.ext.declarative import DeclarativeMeta

# import jsonpickle
# from sqlalchemy.ext.declarative import DeclarativeMeta

__author__ = "bibow"


datetime_format = "%Y-%m-%dT%H:%M:%S%z"
datetime_format_regex_patterns = [
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+|-]\d{4}$",
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+|-]\d{2}:\d{2}$",
]

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


class JSONEncoder(json.JSONEncoder):
    def default(self, o):  # pylint: disable=E0202
        if isinstance(o.__class__, DeclarativeMeta):

            def convert_object_to_dict(obj, found=None):
                if found is None:
                    found = set()

                mapper = orm.class_mapper(obj.__class__)
                columns = [column.key for column in mapper.columns]
                get_key_value = lambda c: (
                    (c, getattr(obj, c).isoformat())
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
            if o.as_integer_ratio()[1] == 1:
                return int(o)
            return float(o)
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

        for key, value in o.items():
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
        return {"message": str(error)}

    @staticmethod
    def json_dumps(data, **kwargs):
        # Use consistent formatting with original jsonencode behavior
        defaults = {
            "compact": False,
            "indent": 2,
            "sort_keys": True,
            "separators": (",", ": "),
        }
        defaults.update(kwargs)
        return Utility.json_handler.dumps(data, **defaults)

    @staticmethod
    def json_loads(data, parser_number=True, parse_datetime=True, **kwargs):
        return Utility.json_handler.loads(
            data, parser_number=parser_number, parse_datetime=parse_datetime, **kwargs
        )

    @staticmethod
    def json_normalize(data, parser_number=True, parse_datetime=True):
        """
        Normalize data types as if going through JSON serialization/deserialization.

        This function simulates json_loads(json_dumps(obj)) without the overhead of
        actual JSON string creation and parsing.

        Args:
            data: Object to normalize
            parser_number: Whether to convert numbers to Decimal after float conversion (default: True)
            parse_datetime: Whether to parse ISO datetime strings back to datetime objects (default: True)

        Returns:
            Normalized object with types as if processed through json_loads(json_dumps(obj))

        Examples:
            # Normalize mixed data types
            data = {
                "amount": Decimal("100.50"),
                "created_at": datetime.now(),
                "items": [Decimal("10"), Decimal("20.5")]
            }
            normalized = Utility.json_normalize(data)
            # Result: Decimal -> float -> Decimal, datetime -> ISO string -> datetime
        """
        return Utility.json_handler.json_normalize(
            data, parser_number=parser_number, parse_datetime=parse_datetime
        )

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

    @staticmethod
    def import_dynamically(
        module_name, function_name, class_name=None, constructor_parameters=None
    ):
        """
        Dynamically imports a module and retrieves a function or method.
        
        This method loads a module dynamically, optionally instantiates a class from that module,
        and returns a callable function or method.
        
        Args:
            module_name (str): The name of the module to import.
            function_name (str): The name of the function/method to retrieve.
            class_name (str, optional): The name of the class containing the method. Defaults to None.
            constructor_parameters (dict, optional): Parameters to pass to the class constructor.
                Defaults to None.
        
        Returns:
            callable or None: The requested function/method if found and accessible, otherwise None.
        
        Raises:
            TypeError: If parameters are of incorrect types.
            ImportError: If the module cannot be imported.
            AttributeError: If the class or function does not exist in the specified module.
        """
        # Validate required parameters
        if not module_name or not function_name:
            return None
        
        # Clean and validate parameters
        try:
            module_name = str(module_name).strip()
            function_name = str(function_name).strip()
            class_name = str(class_name).strip() if class_name else None
        except (TypeError, ValueError) as e:
            raise TypeError(f"Invalid parameter type: {e}")
        
        # Import module directly without find_spec to improve performance
        try:
            module = import_module(module_name)
        except ImportError as e:
            raise ImportError(f"Failed to import module '{module_name}': {e}")
        
        # Handle class instantiation if specified
        target_obj = module
        if class_name:
            # Get class from module
            try:
                cls = getattr(module, class_name)
            except AttributeError as e:
                raise AttributeError(f"Class '{class_name}' not found in module '{module_name}': {e}")
            
            # Instantiate class or use class itself for static methods
            if constructor_parameters is not None:
                if not isinstance(constructor_parameters, dict):
                    raise TypeError("constructor_parameters must be a dictionary")
                target_obj = cls(**constructor_parameters)
            else:
                # Check if method is static before deciding how to get it
                try:
                    method = getattr(cls, function_name)
                    if Utility.is_static_method(method):
                        # For static methods, we can use the class itself
                        target_obj = cls
                    else:
                        # For instance methods, we need to instantiate the class
                        try:
                            target_obj = cls()
                        except Exception as e:
                            raise TypeError(f"Failed to instantiate class '{class_name}': {e}")
                except AttributeError as e:
                    raise AttributeError(f"Method '{function_name}' not found in class '{class_name}': {e}")
        
        # Get the requested function/method
        try:
            return getattr(target_obj, function_name)
        except AttributeError as e:
            raise AttributeError(f"Function '{function_name}' not found in target object: {e}")

    # Call function by async
    @staticmethod
    def call_by_async(callables):
        try:

            async def exec_async_functions(callables):
                if isinstance(callables, list) and callables:
                    return await asyncio.gather(
                        *[
                            fn() if callable(fn) else asyncio.sleep(0)
                            for fn in callables
                        ]
                    )
                elif callable(callables):
                    return await callables()

            return asyncio.run(exec_async_functions(callables))
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

    @staticmethod
    def _invoke_funct_on_local(logger, funct, funct_on_local, setting, **params):
        funct_on_local_class = getattr(
            __import__(funct_on_local["module_name"]),
            funct_on_local["class_name"],
        )
        funct_on_local = getattr(
            funct_on_local_class(
                logger,
                **setting,
            ),
            funct,
        )
        return funct_on_local(**params)

    @staticmethod
    def _invoke_funct_on_aws_lambda(logger, aws_lambda, **kwargs):
        function_name = kwargs.get("function_name", "silvaengine_agenttask")
        invocation_type = kwargs.get("invocation_type", "RequestResponse")
        payload = {
            "endpoint_id": kwargs["endpoint_id"],
            "funct": kwargs["funct"],
            "params": kwargs["params"],
        }
        response = aws_lambda.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=Utility.json_dumps(payload),
        )
        if "FunctionError" in response.keys():
            log = Utility.json_loads(response["Payload"].read())
            logger.error(log)
            raise Exception(log)

        if invocation_type == "RequestResponse":
            return response["Payload"].read().decode("utf-8")

        return

    @staticmethod
    def _invoke_funct_on_aws_sqs(logger, task_queue, message_group_id, **kwargs):
        try:
            task_queue.send_message(
                MessageAttributes={
                    "endpoint_id": {
                        "StringValue": kwargs["endpoint_id"],
                        "DataType": "String",
                    },
                    "funct": {"StringValue": kwargs["funct"], "DataType": "String"},
                },
                MessageBody=Utility.json_dumps({"params": kwargs["params"]}),
                MessageGroupId=message_group_id,
            )
            return
        except Exception as e:
            log = traceback.format_exc()
            logger.error(log)
            raise e

    @staticmethod
    def invoke_funct_on_local(
        logger,
        setting,
        funct,
        **params,
    ):
        try:
            funct_on_local = setting["functs_on_local"].get(funct)
            assert funct_on_local is not None, f"Function ({funct}) not found."

            result = Utility._invoke_funct_on_local(
                logger, funct, funct_on_local, setting, **params
            )
            if result is None:
                return

            result = Utility.json_loads(result)
            if result.get("errors"):
                raise Exception(result["errors"])

            return result["data"]
        except Exception as e:
            log = traceback.format_exc()
            logger.error(log)
            raise e

    @staticmethod
    def invoke_funct_on_aws_lambda(
        logger,
        endpoint_id,
        funct: str,
        params={},
        setting=None,
        test_mode=None,
        aws_lambda=None,
        invocation_type="RequestResponse",
        message_group_id=None,
        task_queue=None,
    ):

        ## Test the waters 🧪 before diving in!
        ##<--Testing Function-->##
        if test_mode:
            if test_mode == "local_for_all":
                # Jump to the local function if these conditions meet.
                return Utility.invoke_funct_on_local(logger, setting, funct, **params)
            elif (
                test_mode == "local_for_sqs" and not message_group_id
            ):  # Test websocket callback with SQS from local.
                # Jump to the local function if these conditions meet.
                return Utility.invoke_funct_on_local(logger, setting, funct, **params)
            elif (
                test_mode == "local_for_aws_lambda" and task_queue is None
            ):  # Test AWS Lambda calls from local.
                pass
        ##<--Testing Function-->##

        # Process SQS message if message group and task queue are provided
        if message_group_id and task_queue:
            Utility._invoke_funct_on_aws_sqs(
                logger,
                task_queue,
                message_group_id,
                **{
                    "endpoint_id": endpoint_id,
                    "funct": funct,
                    "params": params,
                },
            )
            return  # Exit after SQS message sent

        result = Utility._invoke_funct_on_aws_lambda(
            logger,
            aws_lambda,
            **{
                "invocation_type": invocation_type,
                "endpoint_id": endpoint_id,
                "funct": funct,
                "params": params,
            },
        )
        if invocation_type == "Event" or not result or result == "null":
            return

        result = Utility.json_loads(Utility.json_loads(result))
        if "errors" in result:
            raise Exception(result["errors"])

        return result.get("data", result)

    @staticmethod
    def execute_graphql_query(
        logger,
        endpoint_id,
        funct,
        query,
        variables={},
        setting=None,
        connection_id=None,
        test_mode=None,
        aws_lambda=None,
    ):
        params = {
            "query": query,
            "variables": variables,
            "connection_id": connection_id,
        }
        return Utility.invoke_funct_on_aws_lambda(
            logger,
            endpoint_id,
            funct,
            params=params,
            setting=setting,
            test_mode=test_mode,
            aws_lambda=aws_lambda,
        )

    @staticmethod
    def fetch_graphql_schema(
        logger,
        endpoint_id,
        funct,
        setting=None,
        test_mode=None,
        aws_lambda=None,
    ):
        schema = Utility.execute_graphql_query(
            logger,
            endpoint_id,
            funct,
            query=INTROSPECTION_QUERY,
            setting=setting,
            test_mode=test_mode,
            aws_lambda=aws_lambda,
        )["__schema"]
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
            fields = Utility.extract_available_fields(schema, type_name)
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
                        nested_fields = Utility.generate_field_subselection(
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
            Utility.generate_field_subselection(schema, return_type["name"])
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
