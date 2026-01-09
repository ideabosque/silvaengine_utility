#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import asyncio
import inspect
import logging
import threading
import traceback
from importlib import import_module
from importlib.util import find_spec
from queue import Queue
from types import CoroutineType, FunctionType
from typing import Any, Callable, Dict, List, Optional, Union

import boto3

from .cache.decorators import object_cache
from .serializer import Serializer


class Invoker(object):
    @staticmethod
    def is_static_method(method) -> bool:
        return inspect.isfunction(method)

    @staticmethod
    def is_class_method(method) -> bool:
        return (
            inspect.ismethod(method)
            and hasattr(method, "__self__")
            and inspect.isclass(method.__self__)
        )

    @staticmethod
    def is_instance_method(method) -> bool:
        return inspect.ismethod(method)

    @staticmethod
    @object_cache
    def resolve_proxied_callable(
        module_name: str,
        function_name: str,
        class_name: Optional[str] = None,
        constructor_parameters: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Dynamically imports a module and retrieves a function or method.

        Uses thread-safe caching to avoid repeated import operations.
        Cache key format: module_name:class_name:function_name
        Cache has no expiration time (permanent cache).

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
                agent = getattr(agent, class_name)
                agent = agent.__new__(agent)
            except AttributeError as e:
                raise AttributeError(
                    f"Class '{class_name}' not found in module '{module_name}': {e}"
                )

        # Get the requested function/method
        try:
            return getattr(agent, function_name)
        except AttributeError as e:
            raise AttributeError(
                f"Function '{function_name}' not found in target object: {e}"
            )

    @staticmethod
    def _run_async_in_new_thread(coro, result_queue):
        try:
            result_queue.put(asyncio.run(coro))
        except Exception as e:
            result_queue.put(e)

    @staticmethod
    def sync_call_async_compatible(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        else:
            result_queue = Queue()
            thread = threading.Thread(
                target=Invoker._run_async_in_new_thread, args=(coro, result_queue)
            )
            thread.start()
            thread.join()

            result = result_queue.get()

            if isinstance(result, Exception):
                raise result
            return result

    # Call function by async
    @staticmethod
    def call_by_async(function: Callable) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(function())
            loop.close()
            return result
        else:
            task = loop.create_task(function())
            return task

    @staticmethod
    def _invoke_funct_on_local(
        logger: logging.Logger,
        funct: str,
        funct_on_local: Dict[str, Any],
        setting: Dict[str, Any],
        **params: Dict[str, Any],
    ) -> Any:
        funct_on_local_class = getattr(
            __import__(funct_on_local["module_name"]),
            funct_on_local["class_name"],
        )
        funct_on_local_method = getattr(
            funct_on_local_class(
                logger,
                **setting,
            ),
            funct,
        )
        return funct_on_local_method(**params)

    @staticmethod
    def _invoke_funct_on_aws_lambda(
        logger: logging.Logger, aws_lambda: boto3.client, **kwargs: Dict[str, Any]
    ) -> Any:
        function_name = kwargs.get(
            "function_name",
            kwargs.get("setting", {}).get("lambda_task_function"),
        )

        if not function_name and kwargs.get("endpoint_id"):
            function_name = f"{kwargs.get('endpoint_id')}_silvaengine_agenttask"

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
    def _invoke_funct_on_aws_sqs(
        logger: logging.Logger,
        task_queue: boto3.resource,
        message_group_id: str,
        **kwargs: Dict[str, Any],
    ) -> None:
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
        logger: logging.Logger,
        setting: Dict[str, Any],
        funct: str,
        **params: Dict[str, Any],
    ) -> Any:
        try:
            funct_on_local = setting["functs_on_local"].get(funct)
            assert funct_on_local is not None, f"Function ({funct}) not found."

            result = Invoker._invoke_funct_on_local(
                logger, funct, funct_on_local, setting, **params
            )
            if result is None:
                return

            result = Serializer.json_loads(result["body"])

            # Extract data portion to be consistent with AWS Lambda execution path
            if "errors" in result:
                raise Exception(result.get("errors"))
            elif "data" in result:
                return result.get("data")

            return result
        except Exception as e:
            log = traceback.format_exc()
            logger.error(log)
            raise e

    @staticmethod
    def invoke_funct_on_aws_lambda(
        context: Dict[str, Any],
        funct: str,
        params: Dict[str, Any] = {},
        aws_lambda: boto3.client = None,
        invocation_type: str = "RequestResponse",
        message_group_id: Optional[str] = None,
        task_queue: boto3.resource = None,
    ) -> Any:
        logger = context.get("logger")
        endpoint_id = context.get("endpoint_id")
        part_id = context.get("part_id")
        setting = context.get("setting", {})
        execute_mode = setting.get("execute_mode")

        if execute_mode:
            if execute_mode == "local_for_all":
                # Remove context keys that shouldn't be passed to the local function
                # (logger, setting are positional args; endpoint_id, part_id are handled separately)
                local_params = {
                    k: v
                    for k, v in params.items()
                    if k not in ["logger", "setting", "endpoint_id", "part_id"]
                }
                return Invoker.invoke_funct_on_local(
                    logger, setting, funct, **local_params
                )
            if execute_mode == "local_for_sqs" and not message_group_id:
                # Remove context keys that shouldn't be passed to the local function
                local_params = {
                    k: v
                    for k, v in params.items()
                    if k not in ["logger", "setting", "endpoint_id", "part_id"]
                }
                return Invoker.invoke_funct_on_local(
                    logger, setting, funct, **local_params
                )
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
                "function_name": setting.get(
                    "lambda_task_function",
                    f"{endpoint_id}_silvaengine_agenttask",
                ),
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
            raise Exception(result.get("errors"))
        elif "body" in result:
            result = result.get("body")

            if isinstance(result, str):
                result = Serializer.json_loads(result)

        if "data" in result:
            return result.get("data")

        return result
