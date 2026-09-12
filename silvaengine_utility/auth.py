# -*- coding: utf-8 -*-
"""共享鉴权与操作人 ID 工具层。

为 banyan 各业务模块提供统一的 ``operator_id`` 读取与守卫能力，收敛 12 模块
散落的 ``_get_operator_id`` 本地副本（变体 A/B/C 漂移）。

设计原则：
- 克制收敛：仅提供 ``get_operator_id`` / ``require_operator_id`` / 异常类，
  不引入通用鉴权框架、不强制各模块加守卫（守卫补全属各模块 B 组职责）。
- 闭环自洽：``get_operator_id`` 统一为变体 A（返回 ``Optional[str]``，不回退）；
  历史回退 ``or "system"`` 由调用方自行保留（语义不变），避免共享层替业务
  决定回退值。
- 禁止钟摆效应：``require_operator_id`` 缺失时上抛 ``OperatorIdRequiredError``，
  与各模块现有 ``if not operator_id: raise ValueError(...)`` 守卫语义一致，
  仅升级异常类型（结构化错误码），不改变"缺失即拒绝"的行为。

读取 ``info.context`` 的 key 优先级：``user_id`` → ``operator_id``（与各模块
现有变体 A 一致）。``partition_key`` / ``user_name`` 等其它 context 字段
仍由各模块自行读取（业务模块可能附加 ``ip_address`` / ``user_agent`` 等，
不在此收敛）。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AdminAccessRequiredError(Exception):
    """Mutation 需要 admin 权限但当前用户非管理员时抛出。

    网关层 ``PermAuthorizer`` 验证 JWT 后将 ``is_admin`` 注入
    ``info.context``。本守卫读取该字段，缺失或为 False 时拒绝执行，
    防止普通用户调用管理员级写操作（enableUser / disableUser 等）。

    Attributes:
        mutation_name: 触发守卫的 Mutation 名称，用于定位。
        message: 人类可读错误描述。
    """

    def __init__(self, mutation_name: str, message: Optional[str] = None) -> None:
        self.mutation_name = mutation_name
        self.message = message or (
            f"Mutation {mutation_name} 需要管理员权限，"
            f"当前用户不是管理员。"
        )
        super().__init__(self.message)


class OperatorIdRequiredError(Exception):
    """Mutation 缺少 operator_id（操作人 ID）时抛出。

    各模块 ``mutate`` 入口在执行写操作前应通过 ``require_operator_id`` 守卫；
    缺失 operator_id 意味着无法追溯变更来源，违反审计铁律。

    Attributes:
        mutation_name: 触发守卫的 Mutation 名称，用于定位。
        message: 人类可读错误描述。
    """

    def __init__(self, mutation_name: str, message: Optional[str] = None) -> None:
        self.mutation_name = mutation_name
        self.message = message or (
            f"Mutation {mutation_name} 缺少 operator_id（GraphQL context 中"
            f"未提供 user_id / operator_id），拒绝执行以保留审计可追溯性。"
        )
        super().__init__(self.message)


def get_operator_id(info: Any) -> Optional[str]:
    """从 GraphQL context 读取操作人 ID，缺失返回 None。

    读取优先级：``info.context["user_id"]`` → ``info.context["operator_id"]``。
    不在此处回退 ``"system"`` 等默认值（历史变体 B/C 的回退由调用方自行保留，
    语义不变，避免共享层替业务决定回退策略）。

    Args:
        info: GraphQL ``ResolveInfo`` 或含 ``context`` 属性的伪对象。

    Returns:
        操作人 ID 字符串，或 None（缺失时）。
    """
    return info.context.get("user_id") or info.context.get("operator_id")


def require_operator_id(info: Any, mutation_name: str) -> str:
    """守卫函数：返回 operator_id 或抛出 ``OperatorIdRequiredError``。

    用于各模块 ``mutate`` 入口的写操作守卫，统一替代重复的
    ``if not operator_id: raise ValueError(...)`` 模式。缺失即拒绝执行，
    与各模块现有守卫语义一致，仅升级异常类型为结构化错误。

    Args:
        info: GraphQL ``ResolveInfo`` 或含 ``context`` 属性的伪对象。
        mutation_name: Mutation 名称，用于异常定位与日志标识。

    Returns:
        操作人 ID 字符串（非空）。

    Raises:
        OperatorIdRequiredError: ``info.context`` 中无 ``user_id`` /
            ``operator_id`` 时抛出。
    """
    operator_id = get_operator_id(info)
    if not operator_id:
        logger.warning(
            "[auth] Mutation 缺少 operator_id，拒绝执行: mutation=%s",
            mutation_name,
        )
        raise OperatorIdRequiredError(mutation_name)
    return operator_id


def is_admin(info: Any) -> bool:
    """从 GraphQL context 读取 ``is_admin`` 标志。

    网关层 ``PermAuthorizer`` 验证 JWT 后将 ``is_admin`` 注入
    ``info.context``。本函数安全读取该字段，缺失时返回 False。

    Args:
        info: GraphQL ``ResolveInfo`` 或含 ``context`` 属性的伪对象。

    Returns:
        True 如果当前用户拥有管理员角色，否则 False。
    """
    return bool(info.context.get("is_admin", False))


def require_admin(info: Any, mutation_name: str) -> None:
    """守卫函数：校验当前用户是否为管理员，否则抛出 ``AdminAccessRequiredError``。

    用于管理员级写操作（enableUser / disableUser / deleteUser /
    approveMerchant 等）的权限守卫。在 ``require_operator_id`` 之后调用，
    确保操作人已认证且具备管理员角色。

    Args:
        info: GraphQL ``ResolveInfo`` 或含 ``context`` 属性的伪对象。
        mutation_name: Mutation 名称，用于异常定位与日志标识。

    Raises:
        AdminAccessRequiredError: ``info.context["is_admin"]`` 为 False
            或缺失时抛出。
    """
    if not is_admin(info):
        logger.warning(
            "[auth] Mutation 需要管理员权限，拒绝执行: mutation=%s",
            mutation_name,
        )
        raise AdminAccessRequiredError(mutation_name)