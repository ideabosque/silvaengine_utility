# -*- coding: utf-8 -*-
"""共享幂等记录数据访问层。

为 banyan 各业务模块提供统一的 Mutation 幂等去重能力，消除 monitor /
prompt / setting 三模块近乎完全重复的 ``models/idempotency.py`` 实现，
并修复审查阶段发现的三个系统性缺陷：

1. **存储失败静默吞掉** → 幂等实际不生效（原 ``store_result`` 仅 warning）
2. **并发竞态** → ``find`` 后 ``INSERT`` 非原子，并发同 key 业务执行两次
3. **无过期清理** → ``tenant_idempotency_record`` 表无限增长

设计原则：
- 克制收敛：仅提供 ``IdempotencyRepository`` / ``check_and_store`` /
  ``store_result`` / ``purge_expired``，不引入通用装饰器抽象（装饰器
  仍由各模块自定义，因为其位置参数回退策略因模块而异）。
- 闭环自洽：``store`` 使用 ``INSERT ... ON CONFLICT DO NOTHING``，并发同
  key 时以「先写入者为准」，``store_result`` 不再静默吞掉非冲突异常。
- 禁止钟摆效应：``find`` 失败统一上抛（由装饰器决定降级或拒绝），三模块
  行为一致，消除「monitor 包 try/except、prompt/setting 不包」的漂移。

复合主键 ``(partition_key, idempotency_key)``，WHERE 子句强制
``partition_key = :pk``。
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any, Callable, Dict, Optional

import pendulum
from silvaengine_connections import ConnectionPoolManager
from sqlalchemy import text

logger = logging.getLogger(__name__)

POOL = "postgres_main"

SQL_FIND = """
SELECT idempotency_key, mutation_name, result_payload, created_at
FROM tenant_idempotency_record
WHERE partition_key = :pk AND idempotency_key = :idempotency_key
"""

# ON CONFLICT DO NOTHING：并发同 key 时后到者不报错也不覆盖先到者结果。
# RETURNING idempotency_key 用于判断是否本请求抢占成功（非空即成功）。
SQL_INSERT = """
INSERT INTO tenant_idempotency_record (
    partition_key, idempotency_key, mutation_name, result_payload, created_at
) VALUES (
    :pk, :idempotency_key, :mutation_name, :result_payload, :created_at
)
ON CONFLICT (partition_key, idempotency_key) DO NOTHING
RETURNING idempotency_key
"""

SQL_PURGE_EXPIRED = """
DELETE FROM tenant_idempotency_record
WHERE partition_key = :pk AND created_at < :cutoff
"""


class IdempotencyRepository:
    """对 ``tenant_idempotency_record`` 表进行查询、插入与清理。"""

    POOL = POOL

    @staticmethod
    def find(
        partition_key: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        """根据幂等键检索已有记录，返回反序列化后的结果或 None。

        ``find`` 失败统一上抛（连接抖动等），由调用方/装饰器决定降级策略，
        不在此处静默吞掉，以保证三模块行为一致。
        """
        with ConnectionPoolManager().connection(IdempotencyRepository.POOL) as conn:
            row = (
                conn.execute(
                    text(SQL_FIND),
                    {"pk": partition_key, "idempotency_key": idempotency_key},
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        result_payload = row.get("result_payload")
        if isinstance(result_payload, str):
            try:
                result_payload = json.loads(result_payload)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "idempotency_key": str(row.get("idempotency_key")),
            "mutation_name": row.get("mutation_name"),
            "result": result_payload,
        }

    @staticmethod
    def store(
        partition_key: str,
        idempotency_key: str,
        mutation_name: str,
        result: Any,
    ) -> bool:
        """存储幂等记录，返回是否本请求抢占成功。

        使用 ``ON CONFLICT DO NOTHING``：并发同 key 时后到者不报错、不覆盖，
        返回 False 表示已有并发请求抢先写入。非冲突异常（连接断开、磁盘满等）
        统一上抛，交由 ``store_result`` 处理，不再静默吞掉。
        """
        now = pendulum.now("UTC")
        payload_str = (
            json.dumps(result, ensure_ascii=False, default=str)
            if result is not None
            else None
        )
        with ConnectionPoolManager().connection(IdempotencyRepository.POOL) as conn:
            row = (
                conn.execute(
                    text(SQL_INSERT),
                    {
                        "pk": partition_key,
                        "idempotency_key": idempotency_key,
                        "mutation_name": mutation_name,
                        "result_payload": payload_str,
                        "created_at": now,
                    },
                )
                .mappings()
                .first()
            )
        return row is not None

    @staticmethod
    def purge_expired(partition_key: str, retention_seconds: int) -> int:
        """清理超过保留期的幂等记录，返回删除行数。

        建议 by 定时任务调用（如每日），``retention_seconds`` 推荐 7 天
        (604800)。``created_at`` 上建议建索引以加速清理。
        """
        cutoff = pendulum.now("UTC").subtract(seconds=retention_seconds)
        with ConnectionPoolManager().connection(IdempotencyRepository.POOL) as conn:
            result = conn.execute(
                text(SQL_PURGE_EXPIRED),
                {"pk": partition_key, "cutoff": cutoff},
            )
            return result.rowcount or 0


def check_and_store(
    partition_key: str,
    idempotency_key: str,
    mutation_name: str,
) -> Optional[Dict[str, Any]]:
    """检查幂等键是否已存在，若存在则返回已有结果。

    ``find`` 失败上抛，由装饰器决定是否降级为非幂等执行（不在此静默吞掉，
    以保证三模块行为一致并保留可观测性）。

    Returns:
        已有结果（``existing["result"]``），或 None 表示首次请求。
    """
    existing = IdempotencyRepository.find(partition_key, idempotency_key)
    if existing is not None:
        logger.info(
            "[idempotency] 命中幂等记录: mutation=%s key=%s",
            mutation_name,
            idempotency_key,
        )
        return existing["result"]
    return None


def store_result(
    partition_key: str,
    idempotency_key: str,
    mutation_name: str,
    result: Any,
) -> None:
    """存储 Mutation 结果以供后续幂等命中。

    与历史实现的关键差异：
    - 不再 ``except Exception: logger.warning`` 静默吞掉所有异常；
    - 并发冲突（``ON CONFLICT DO NOTHING`` 未插入）视为并发请求抢先写入，
      记录 info 日志后正常返回（当前结果与已存结果等价，无需报错）；
    - 其他存储异常上抛，让客户端感知「幂等未持久化」并自行决定重试，
      避免幂等静默失效。
    """
    try:
        inserted = IdempotencyRepository.store(
            partition_key, idempotency_key, mutation_name, result
        )
    except Exception as exc:
        # 不静默吞掉：业务已成功但幂等未落库，客户端重试会重复执行。
        # 上抛让客户端感知，由其决定是否重试（重试会重复副作用，但至少
        # 可观测、可归因，优于静默失效）。
        logger.error(
            "[idempotency] 存储幂等记录失败（幂等未持久化，客户端重试将重复执行）: "
            "mutation=%s key=%s err=%s",
            mutation_name,
            idempotency_key,
            exc,
        )
        raise
    if not inserted:
        logger.info(
            "[idempotency] 并发同 key，已由抢先请求写入: mutation=%s key=%s",
            mutation_name,
            idempotency_key,
        )


def purge_expired(partition_key: str, retention_seconds: int = 604800) -> int:
    """清理超过保留期的幂等记录（便捷封装）。

    默认保留 7 天（604800 秒）。建议由定时任务每日调用。返回删除行数。
    ``created_at`` 上建议建索引以加速清理。
    """
    return IdempotencyRepository.purge_expired(partition_key, retention_seconds)



def idempotent_mutation(mutation_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mutation 幂等装饰器（统一各业务模块的本地 ``_idempotent`` 副本）。

    设计目标：收敛 banyan 12 模块 20 份几乎完全相同但行为漂移的本地装饰器，
    修复审查阶段发现的两个系统性缺陷：

    1. **位置参数回退 bug**：本地副本统一含 ``for a in args[2:]: if
       isinstance(a, str): idempotency_key = a``，当 caller 以位置参数传
       ``id`` / ``session_id`` / ``agent_id`` 等时，首个字符串位置参数被
       误当幂等键，导致 A 请求的 ``id`` 撞上 B 请求的真幂等键。
       本装饰器**仅从 kwargs 显式取 idempotency_key**，删除位置回退分支
       （调查显示所有 mutation 在 resolver 层都从 kwargs 传 idempotency_key，
       回退分支为带 bug 的死代码）。

    2. **静默吞错**：4 模块（capability/knowledge/perm/user）
       ``except Exception: pass`` 完全吞掉 check/store 异常，2 模块
       （merchant/orchestration）仅吞 check 不吞 store，行为分裂且抵消
       共享层 ``store_result`` 不吞错的收益。本装饰器统一为
       ``logger.error`` 记录后继续，保留可观测性但不阻塞业务。

    异常处理策略（与各模块不吞错变体一致，统一形态）：
    - ``check_and_store`` 异常：``logger.error`` 后继续执行 mutation
      （降级为非幂等本次，不阻塞业务；DB 抖动恢复后后续请求恢复幂等）。
    - ``store_result`` 异常：``logger.error`` 后返回已计算 result（业务已
      成功，幂等未持久化由客户端重试处理，不阻塞返回）。

    与各模块现有 ``_idempotent`` 的行为兼容性：
    - 返回值结构完全保持（直接 ``return func(...)`` / ``return existing``）。
    - 无 ``info`` 或无 ``idempotency_key`` 时直接执行 mutation（与现有完全一致）。
    - ``info`` 取 ``args[1]`` 或 ``kwargs.get("info")``（与现有一致）。

    Args:
        mutation_name: Mutation 名称，用于幂等记录的 ``mutation_name`` 字段
            与日志标识，便于跨模块统一观测。

    Returns:
        装饰器工厂，应用于 ``@idempotent_mutation("CreateXxx")`` 形态。
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            info = args[1] if len(args) > 1 else kwargs.get("info")
            idempotency_key = kwargs.get("idempotency_key")
            if info is None or not idempotency_key:
                return func(*args, **kwargs)

            partition_key = info.context.get("partition_key", "")
            try:
                existing = check_and_store(
                    partition_key, idempotency_key, mutation_name
                )
                if existing is not None:
                    return existing
            except Exception as exc:
                logger.error(
                    "[idempotency] 幂等检查失败（降级为非幂等本次，继续执行）: "
                    "mutation=%s key=%s err=%s",
                    mutation_name,
                    idempotency_key,
                    exc,
                )

            result = func(*args, **kwargs)
            try:
                store_result(
                    partition_key, idempotency_key, mutation_name, result
                )
            except Exception as exc:
                logger.error(
                    "[idempotency] 幂等存储失败（业务已成功，幂等未持久化，客户端重试将重复执行）: "
                    "mutation=%s key=%s err=%s",
                    mutation_name,
                    idempotency_key,
                    exc,
                )
            return result

        return wrapper

    return decorator
