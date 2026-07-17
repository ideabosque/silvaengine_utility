# -*- coding: utf-8 -*-
"""WebSocket 流式推送工具。

封装 AWS API Gateway WebSocket 的 ``post_to_connection`` API，
用于 GraphQL subscription 事件推送。

依赖 ``boto3`` 创建 ``apigatewaymanagementapi`` 客户端。
endpoint URL 从 setting 或环境变量获取。
"""

from __future__ import print_function

import logging
import os
from typing import Any, Dict, Optional

import boto3

from .serializer import Serializer


class WebSocketStreamer:
    """WebSocket 事件推送器。

    封装 ``ApiGatewayManagementApi.post_to_connection()``，
    将 GraphQL subscription 事件序列化后推送到客户端。

    endpoint URL 解析优先级：
    1. ``setting["websocket_endpoint_url"]`` — 显式配置
    2. 环境变量 ``WEBSOCKET_ENDPOINT_URL``
    3. 从 ``aws_api_area`` + ``aws_api_stage`` 组合推断
    """

    def __init__(
        self,
        connection_id: str,
        aws_api_stage: Optional[str],
        aws_api_area: Optional[str],
        setting: Dict[str, Any],
        logger: Optional[logging.Logger],
    ) -> None:
        self.connection_id = connection_id
        self.aws_api_stage = aws_api_stage
        self.aws_api_area = aws_api_area
        self.setting = setting if isinstance(setting, dict) else {}
        self.logger = logger
        self._client: Optional[Any] = None

    def _resolve_endpoint_url(self) -> str:
        """解析 WebSocket endpoint URL。"""
        # 优先级 1：setting 显式配置
        url = self.setting.get("websocket_endpoint_url")
        if url:
            return str(url)

        # 优先级 2：环境变量
        url = os.getenv("WEBSOCKET_ENDPOINT_URL")
        if url:
            return str(url)

        # 优先级 3：从 area + stage 推断
        if self.aws_api_area and self.aws_api_stage:
            return f"https://{self.aws_api_area}/{self.aws_api_stage}"

        raise ValueError(
            "Cannot resolve WebSocket endpoint URL. "
            "Set setting['websocket_endpoint_url'] or env WEBSOCKET_ENDPOINT_URL."
        )

    @property
    def client(self) -> Any:
        """惰性创建 apigatewaymanagementapi 客户端。"""
        if self._client is None:
            endpoint_url = self._resolve_endpoint_url()
            region = os.getenv("REGION_NAME", os.getenv("REGIONNAME", "us-east-1"))
            self._client = boto3.client(
                "apigatewaymanagementapi",
                endpoint_url=endpoint_url,
                region_name=region,
            )
        return self._client

    async def send(self, payload: Dict[str, Any]) -> None:
        """推送单个事件到 WebSocket 客户端。

        Args:
            payload: 事件数据字典，将 JSON 序列化后发送。

        实现说明：``post_to_connection`` 是同步 boto3 调用，
        用 ``asyncio.to_thread`` 包装避免阻塞 event loop。
        为后续 ReAct 步骤级流式（高频推送）预留非阻塞语义。
        """
        import asyncio

        data = Serializer.json_dumps(payload).encode("utf-8")
        try:
            await asyncio.to_thread(
                self.client.post_to_connection,
                ConnectionId=self.connection_id,
                Data=data,
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    "WebSocket push failed for connection %s: %s",
                    self.connection_id,
                    e,
                )
            raise
