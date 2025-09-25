from io import StringIO
from types import SimpleNamespace

import pytest

from silvaengine_utility.utility import Utility


class StubLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def test_execute_mode_prefers_local(monkeypatch):
    logger = StubLogger()
    called = {}

    def fake_local(logger_arg, setting, funct, **params):
        called["local"] = (logger_arg, funct, params)
        return "local-result"

    def fail_remote(*args, **kwargs):
        raise AssertionError("Remote invocation should not run when execute_mode is local")

    monkeypatch.setattr(Utility, "invoke_funct_on_local", staticmethod(fake_local))
    monkeypatch.setattr(Utility, "_invoke_funct_on_aws_lambda", staticmethod(fail_remote))

    result = Utility.invoke_funct_on_aws_lambda(
        logger,
        endpoint_id="ep-1",
        funct="do_work",
        params={"value": 1},
        setting={},
        execute_mode="local_for_all",
    )

    assert result == "local-result"
    assert "local" in called


def test_test_mode_triggers_deprecation_warning(monkeypatch):
    logger = StubLogger()

    def fake_remote(*args, **kwargs):
        inner = Utility.json_dumps({"data": {"result": True}})
        return Utility.json_dumps(inner)

    monkeypatch.setattr(Utility, "_invoke_funct_on_aws_lambda", staticmethod(fake_remote))

    with pytest.warns(DeprecationWarning):
        result = Utility.invoke_funct_on_aws_lambda(
            logger,
            endpoint_id="ep-2",
            funct="do_work",
            params={"value": 2},
            setting={},
            test_mode="local_for_aws_lambda",
            aws_lambda=SimpleNamespace(),
        )

    assert result == {"result": True}


def test_execute_mode_overrides_test_mode(monkeypatch):
    logger = StubLogger()
    calls = {}

    def fake_remote(*args, **kwargs):
        calls["remote"] = True
        inner = Utility.json_dumps({"data": {"value": 3}})
        return Utility.json_dumps(inner)

    monkeypatch.setattr(Utility, "_invoke_funct_on_aws_lambda", staticmethod(fake_remote))

    with pytest.warns(UserWarning):
        data = Utility.invoke_funct_on_aws_lambda(
            logger,
            endpoint_id="ep-3",
            funct="do_work",
            params={},
            setting={},
            test_mode="local_for_all",
            execute_mode="remote_only",
            aws_lambda=SimpleNamespace(),
        )

    assert calls.get("remote") is True
    assert data == {"value": 3}


def test_message_routed_to_sqs(monkeypatch):
    logger = StubLogger()
    recorded = {}

    def fake_sqs(logger_arg, queue, group_id, **kwargs):
        recorded["payload"] = kwargs
        recorded["group"] = group_id

    monkeypatch.setattr(Utility, "_invoke_funct_on_aws_sqs", staticmethod(fake_sqs))

    Utility.invoke_funct_on_aws_lambda(
        logger,
        endpoint_id="ep-4",
        funct="do_work",
        params={"ping": True},
        setting={},
        execute_mode=None,
        task_queue=SimpleNamespace(),
        message_group_id="group-1",
    )

    assert recorded["group"] == "group-1"
    assert recorded["payload"] == {
        "endpoint_id": "ep-4",
        "funct": "do_work",
        "params": {"ping": True},
    }
