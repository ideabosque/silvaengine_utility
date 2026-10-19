# -*- coding: utf-8 -*-
"""共享层 ``idempotent_mutation`` 装饰器与 ``auth`` helper 单元测试。

覆盖 C 组系统性收敛新增的共享能力：
- ``silvaengine_utility.idempotency.idempotent_mutation``：仅从 kwargs 取
  idempotency_key（禁止位置回退）、check/store 异常 logger.error 后继续
  （不阻塞业务）。
- ``silvaengine_utility.auth.get_operator_id`` / ``require_operator_id`` /
  ``OperatorIdRequiredError``：操作人 ID 读取与守卫。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from silvaengine_utility.auth import (
    OperatorIdRequiredError,
    get_operator_id,
    require_operator_id,
)
from silvaengine_utility.idempotency import idempotent_mutation


# ---------------------------------------------------------------------------
# auth helper
# ---------------------------------------------------------------------------


class TestGetOperatorId:
    """``get_operator_id`` 读取优先级与回退。"""

    def test_returns_user_id_when_present(self):
        info = SimpleNamespace(context={"user_id": "u-1"})
        assert get_operator_id(info) == "u-1"

    def test_falls_back_to_operator_id_when_user_id_missing(self):
        info = SimpleNamespace(context={"operator_id": "op-2"})
        assert get_operator_id(info) == "op-2"

    def test_user_id_takes_precedence_over_operator_id(self):
        info = SimpleNamespace(context={"user_id": "u-1", "operator_id": "op-2"})
        assert get_operator_id(info) == "u-1"

    def test_returns_none_when_both_missing(self):
        info = SimpleNamespace(context={})
        assert get_operator_id(info) is None


class TestRequireOperatorId:
    """``require_operator_id`` 守卫与异常。"""

    def test_returns_operator_id_when_present(self):
        info = SimpleNamespace(context={"user_id": "u-1"})
        assert require_operator_id(info, "CreateXxx") == "u-1"

    def test_raises_operator_id_required_error_when_missing(self):
        info = SimpleNamespace(context={})
        with pytest.raises(OperatorIdRequiredError) as exc_info:
            require_operator_id(info, "DeleteYyy")
        assert exc_info.value.mutation_name == "DeleteYyy"
        assert "DeleteYyy" in str(exc_info.value)

    def test_error_message_contains_mutation_name(self):
        info = SimpleNamespace(context={})
        with pytest.raises(OperatorIdRequiredError) as exc_info:
            require_operator_id(info, "UpdateZzz")
        assert "UpdateZzz" in exc_info.value.message


# ---------------------------------------------------------------------------
# idempotent_mutation decorator
# ---------------------------------------------------------------------------


def _info(pk="pk-1"):
    """构造含 partition_key 的伪 info 对象。"""
    return SimpleNamespace(context={"partition_key": pk})


class TestIdempotentMutationKeyRetrieval:
    """装饰器仅从 kwargs 取 idempotency_key，禁止位置回退。"""

    def test_no_idempotency_key_executes_mutation(self):
        calls = []

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            calls.append(1)
            return {"node": "ok"}

        assert mutate(None, _info()) == {"node": "ok"}
        assert mutate(None, _info()) == {"node": "ok"}
        assert len(calls) == 2

    def test_positional_string_arg_not_treated_as_idempotency_key(self):
        """位置参数为 str（如 id/session_id）时不应被误当幂等键。

        回归历史 bug：本地装饰器 ``for a in args[2:]: if isinstance(a, str)``
        会把位置参数 id 当 idempotency_key，导致 A 请求的 id 撞上 B 请求的真幂等键。
        共享装饰器删除位置回退分支，仅从 kwargs 取 idempotency_key。
        """
        calls = []

        @idempotent_mutation("Mut")
        def mutate(root, info, some_id, **kwargs):
            calls.append(some_id)
            return {"id": some_id}

        # 两次调用传不同位置 str，但都没传 idempotency_key → 不应命中幂等
        mutate(None, _info(), "id-aaa")
        mutate(None, _info(), "id-bbb")
        assert calls == ["id-aaa", "id-bbb"]

    def test_kwargs_only_idempotency_key_is_used(self):
        """显式从 kwargs 传 idempotency_key 时走幂等路径。"""
        calls = []

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            calls.append(1)
            return {"node": "ok"}

        with patch("silvaengine_utility.idempotency.check_and_store") as mock_check, \
             patch("silvaengine_utility.idempotency.store_result") as mock_store:
            mock_check.return_value = None
            assert mutate(None, _info(), idempotency_key="k1") == {"node": "ok"}
            assert mock_check.call_count == 1
            assert mock_store.call_count == 1
        assert len(calls) == 1


class TestIdempotentMutationExistingCache:
    """命中已有记录时直接返回，不执行 mutation、不存储。"""

    def test_returns_cached_result_when_existing_found(self):
        cached = {"node": "cached-result"}

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            raise AssertionError("不应被执行，命中缓存应直接返回")

        with patch("silvaengine_utility.idempotency.check_and_store") as mock_check, \
             patch("silvaengine_utility.idempotency.store_result") as mock_store:
            mock_check.return_value = cached
            assert mutate(None, _info(), idempotency_key="k1") == cached
            assert mock_store.call_count == 0


class TestIdempotentMutationErrorHandling:
    """check/store 异常 logger.error 后继续，不阻塞业务。"""

    def test_check_failure_does_not_block_mutation(self, caplog):
        """check_and_store 抛异常时降级为非幂等，继续执行 mutation 并存储。"""
        calls = []

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            calls.append(1)
            return {"node": "ok"}

        with patch("silvaengine_utility.idempotency.check_and_store") as mock_check, \
             patch("silvaengine_utility.idempotency.store_result") as mock_store:
            mock_check.side_effect = RuntimeError("db connection lost")
            mock_store.return_value = None
            result = mutate(None, _info(), idempotency_key="k1")
            assert result == {"node": "ok"}
            assert mock_store.call_count == 1
        assert len(calls) == 1

    def test_store_failure_does_not_block_return(self, caplog):
        """store_result 抛异常时 logger.error 后返回已计算 result，不阻塞。"""
        calls = []

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            calls.append(1)
            return {"node": "ok"}

        with patch("silvaengine_utility.idempotency.check_and_store") as mock_check, \
             patch("silvaengine_utility.idempotency.store_result") as mock_store:
            mock_check.return_value = None
            mock_store.side_effect = RuntimeError("disk full")
            result = mutate(None, _info(), idempotency_key="k1")
            assert result == {"node": "ok"}
        assert len(calls) == 1

    def test_no_info_skips_idempotency(self):
        calls = []

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            calls.append(1)
            return {"node": "ok"}

        assert mutate(None, None, idempotency_key="k1") == {"node": "ok"}
        assert len(calls) == 1


class TestIdempotentMutationReturnStructure:
    """装饰器返回值结构与调用方契约保持一致。"""

    def test_returns_dict_unchanged(self):
        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            return {"node": {"id": "x"}, "ok": True}

        with patch("silvaengine_utility.idempotency.check_and_store") as mock_check, \
             patch("silvaengine_utility.idempotency.store_result"):
            mock_check.return_value = None
            r = mutate(None, _info(), idempotency_key="k1")
        assert r == {"node": {"id": "x"}, "ok": True}

    def test_returns_cached_dict_unchanged(self):
        cached = {"node": {"id": "y"}, "ok": True}

        @idempotent_mutation("Mut")
        def mutate(root, info, **kwargs):
            raise AssertionError

        with patch("silvaengine_utility.idempotency.check_and_store") as mock_check, \
             patch("silvaengine_utility.idempotency.store_result") as mock_store:
            mock_check.return_value = cached
            r = mutate(None, _info(), idempotency_key="k1")
            assert mock_store.call_count == 0
        assert r == cached