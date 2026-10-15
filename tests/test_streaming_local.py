# -*- coding: utf-8 -*-
"""WebSocketStreamer local delivery (self-hosted gateway ConnectionManager)."""

import asyncio
import json

import pytest

from silvaengine_utility import streaming
from silvaengine_utility.streaming import WebSocketStreamer


class _Manager:
    def __init__(self, owns):
        self.owns = owns
        self.sent = []

    def send_to_connection(self, connection_id, data):
        if connection_id not in self.owns:
            return False
        self.sent.append((connection_id, json.loads(data)))
        return True


def _streamer(conn):
    return WebSocketStreamer(conn, None, None, {}, None)


@pytest.fixture(autouse=True)
def _reset():
    yield
    streaming.set_local_connection_manager(None)


def test_local_manager_delivers_owned_connection():
    manager = _Manager({"c1"})
    streaming.set_local_connection_manager(manager)
    asyncio.run(_streamer("c1").send({"data": {"x": 1}}))
    assert manager.sent == [("c1", {"data": {"x": 1}})]


def test_falls_back_to_aws_when_manager_does_not_own_connection(monkeypatch):
    streaming.set_local_connection_manager(_Manager(set()))
    calls = []

    class _Client:
        def post_to_connection(self, ConnectionId, Data):
            calls.append((ConnectionId, json.loads(Data)))

    s = _streamer("c2")
    s._client = _Client()
    asyncio.run(s.send({"data": 2}))
    assert calls == [("c2", {"data": 2})]
