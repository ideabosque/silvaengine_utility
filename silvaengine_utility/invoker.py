#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import asyncio
import traceback
from importlib import import_module
from importlib.util import find_spec
from types import FunctionType
from typing import Any, Dict

from .serializer import Serializer
from .utility import Utility


class Invoker(object):
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
            raise ValueError("module_name and function_name are required")

        # Clean and validate parameters
        try:
            module_name = str(module_name).strip()
            function_name = str(function_name).strip()
            class_name = str(class_name).strip() if class_name else None
        except (TypeError, ValueError) as e:
            raise TypeError(f"Invalid parameter type: {e}")

        # Import module directly without find_spec to improve performance
        try:
            if find_spec(name=module_name, package=module_name) is None:
                raise ModuleNotFoundError(f"Module spec for '{module_name}' not found")

            agent = import_module(module_name)
        except Exception as e:
            raise e

        # Handle class instantiation if specified
        if class_name:
            # Get class from module
            try:
                cls = getattr(agent, class_name)
            except AttributeError as e:
                raise AttributeError(
                    f"Class '{class_name}' not found in module '{module_name}': {e}"
                )

            # Instantiate class or use class itself for static methods
            if constructor_parameters is not None:
                if not isinstance(constructor_parameters, dict):
                    raise TypeError("constructor_parameters must be a dictionary")
                agent = cls(**constructor_parameters)
            else:
                # Check if method is static before deciding how to get it
                try:
                    method = getattr(cls, function_name)
                    if Invoker.is_static_method(method):
                        # For static methods, we can use the class itself
                        agent = cls
                    else:
                        # For instance methods, we need to instantiate the class
                        try:
                            agent = cls()
                        except Exception as e:
                            raise TypeError(
                                f"Failed to instantiate class '{class_name}': {e}"
                            )
                except AttributeError as e:
                    raise AttributeError(
                        f"Method '{function_name}' not found in class '{class_name}': {e}"
                    )

        # Get the requested function/method
        try:
            return getattr(agent, function_name)
        except AttributeError as e:
            raise AttributeError(
                f"Function '{function_name}' not found in target object: {e}"
            )

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
        function_name = kwargs.get(
            "function_name",
            kwargs.get("setting", {}).get("lambda_task_function"),
        )

        if not function_name and kwargs.get("endpoint_id"):
            function_name = f"{kwargs.get('endpoint_id')}_silvaengine_microcore"

        invocation_type = kwargs.get("invocation_type", "RequestResponse")
        payload = {
            "endpoint_id": kwargs["endpoint_id"],
            "part_id": kwargs["part_id"],
            "funct": kwargs["funct"],
            "params": kwargs["params"],
        }
        print("=" * 80)
        print(f"function_name: {function_name}")
        print(f"invocation_type: {invocation_type}")
        print(f"payload: {payload}")
        print("=" * 80)

        response = aws_lambda.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=Serializer.json_dumps(payload),
        )
        if "FunctionError" in response.keys():
            log = Serializer.json_loads(response["Payload"].read())
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
                    "part_id": {
                        "StringValue": kwargs["part_id"],
                        "DataType": "String",
                    },
                    "funct": {"StringValue": kwargs["funct"], "DataType": "String"},
                },
                MessageBody=Serializer.json_dumps({"params": kwargs["params"]}),
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

            result = Invoker._invoke_funct_on_local(
                logger, funct, funct_on_local, setting, **params
            )
            if result is None:
                return

            result = Serializer.json_loads(result["body"])

            return result
        except Exception as e:
            log = traceback.format_exc()
            logger.error(log)
            raise e

    @staticmethod
    def invoke_funct_on_aws_lambda(
        context: Dict[str, Any],
        funct: str,
        params={},
        aws_lambda=None,
        invocation_type="RequestResponse",
        message_group_id=None,
        task_queue=None,
    ):
        logger = context.get("logger")
        endpoint_id = context.get("endpoint_id")
        part_id = context.get("part_id")
        setting = context.get("setting", {})
        execute_mode = setting.get("execute_mode")

        if execute_mode:
            if execute_mode == "local_for_all":
                return Invoker.invoke_funct_on_local(logger, setting, funct, **params)
            if execute_mode == "local_for_sqs" and not message_group_id:
                return Invoker.invoke_funct_on_local(logger, setting, funct, **params)
            if execute_mode == "local_for_aws_lambda" and task_queue is None:
                pass

        if message_group_id and task_queue:
            Invoker._invoke_funct_on_aws_sqs(
                logger,
                task_queue,
                message_group_id,
                **{
                    "endpoint_id": endpoint_id,
                    "part_id": part_id,
                    "funct": funct,
                    "params": params,
                },
            )
            return

        result = Invoker._invoke_funct_on_aws_lambda(
            logger,
            aws_lambda,
            **{
                "invocation_type": invocation_type,
                "endpoint_id": endpoint_id,
                "part_id": part_id,
                "funct": funct,
                "params": params,
                "setting": setting,
            },
        )
        if invocation_type == "Event" or not result or result == "null":
            return

        # Handle double JSON decoding safely
        try:
            # First decode
            first_decode = Serializer.json_loads(result)
            # Second decode (might fail if already decoded)
            if isinstance(first_decode, str):
                result = Serializer.json_loads(first_decode)
            else:
                result = first_decode
        except Exception as e:
            # If double decoding fails, try single decode
            result = Serializer.json_loads(result)

        if "errors" in result:
            raise Exception(result["errors"])

        return result["data"]
