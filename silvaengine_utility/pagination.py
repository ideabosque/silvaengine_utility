# -*- coding: utf-8 -*-
"""共享分页工具（raw SQL 友好）。

为 banyan 各业务模块提供统一的 Relay Connection 分页构造能力，
消除各模块重复实现的 encode_cursor / decode_cursor / build_connection
/ PageInfoType 代码。本模块刻意保持克制：

- 不依赖 SQLAlchemy ORM Query，仅依赖 graphene + base64 + json；
- 仅提供工具函数与一个 PageInfoType，不引入「通用 Connection Field」
  抽象（避免过度设计）；
- 同时支持 offset cursor 与 keyset cursor 两种格式，decode_cursor
  自动识别。

设计原则：
1. 禁止钟摆效应 —— 同一字段在 offset 与 keyset 之间不得混用；
2. 禁止过度设计 —— 不为「未来可能」的第三种分页方式预留扩展点；
3. 闭环自洽 —— build_connection 的输出结构必须与各模块既有
   ConnectionType 字段（edges / page_info / total_count）完全一致。
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

import graphene

__all__ = [
    "MAX_PAGE_LIMIT",
    "DEFAULT_PAGE_SIZE",
    "PageInfoType",
    "encode_offset_cursor",
    "decode_offset_cursor",
    "encode_keyset_cursor",
    "decode_keyset_cursor",
    "decode_cursor",
    "build_connection",
    "restore_keyset_value",
    "build_keyset_where_clause",
    "build_keyset_connection_no_count",
]

#: 全局分页上限，各模块应通过 min(first, MAX_PAGE_LIMIT) 强制约束。
MAX_PAGE_LIMIT = 100

#: 默认页大小，first 为空或非正时使用。
DEFAULT_PAGE_SIZE = 20


class PageInfoType(graphene.ObjectType):
    """Relay PageInfo 标准结构（与各模块既有定义保持一致）。"""

    has_next_page = graphene.Boolean(required=True)
    has_previous_page = graphene.Boolean(required=True)
    start_cursor = graphene.String()
    end_cursor = graphene.String()


# ---------------------------------------------------------------------------
# Offset cursor —— base64(str(offset))，兼容各模块既有格式
# ---------------------------------------------------------------------------

def encode_offset_cursor(offset: int) -> str:
    """将 offset 编码为 base64 cursor。"""
    return base64.b64encode(str(offset).encode("utf-8")).decode("utf-8")


def decode_offset_cursor(cursor: Optional[str]) -> int:
    """将 base64 cursor 解码为 offset；失败或空返回 0。"""
    if not cursor:
        return 0
    try:
        return int(base64.b64decode(cursor.encode("utf-8")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 0


# ---------------------------------------------------------------------------
# Keyset cursor —— base64(json({"v": sort_value, "id": id_value}))
# ---------------------------------------------------------------------------

def encode_keyset_cursor(payload: Dict[str, Any]) -> Optional[str]:
    """将 keyset 定位信息编码为 base64(json) cursor。

    payload 至少应包含排序字段的值。约定键名：
    - ``v``: 排序键的值（如 updated_at / created_at / id）
    - ``id``: 唯一标识，用于在 v 相同时稳定排序
    """
    if not payload:
        return None
    return base64.b64encode(
        json.dumps(payload, default=str).encode("utf-8")
    ).decode("utf-8")


def decode_keyset_cursor(cursor: Optional[str]) -> Optional[Dict[str, Any]]:
    """将 keyset cursor 解码为 dict；失败或空返回 None。"""
    if not cursor:
        return None
    try:
        return json.loads(base64.b64decode(cursor.encode("utf-8")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def decode_cursor(cursor: Optional[str]) -> int:
    """向后兼容的 cursor 解码：优先按 offset 格式解码。

    注意：keyset 分页的 resolver 不应使用本函数，应直接调用
    ``decode_keyset_cursor``。本函数仅为迁移期 offset 模式提供统一入口。
    """
    return decode_offset_cursor(cursor)


# ---------------------------------------------------------------------------
# build_connection —— 统一构造 Relay Connection 响应结构
# ---------------------------------------------------------------------------

def build_connection(
    items: List[Dict[str, Any]],
    total_count: int,
    first: Optional[int],
    after: Optional[str],
) -> Dict[str, Any]:
    """构造 Relay Connection 响应（offset 模式）。

    输出结构严格对齐各模块 ConnectionType 的字段：
    ``{"edges": [...], "page_info": {...}, "total_count": int}``
    """
    page_size = first if first and first > 0 else DEFAULT_PAGE_SIZE
    offset = decode_offset_cursor(after)

    edges: List[Dict[str, Any]] = [
        {
            "node": item,
            "cursor": encode_offset_cursor(offset + idx + 1),
        }
        for idx, item in enumerate(items)
    ]
    end_offset = offset + len(items)
    page_info = {
        "has_next_page": end_offset < total_count,
        "has_previous_page": offset > 0,
        "start_cursor": encode_offset_cursor(offset) if items else None,
        "end_cursor": encode_offset_cursor(end_offset) if items else None,
    }
    return {
        "edges": edges,
        "page_info": page_info,
        "total_count": total_count,
    }


# ---------------------------------------------------------------------------
# Keyset Connection 构造 + PaginationMode enum
# ---------------------------------------------------------------------------

class PaginationMode:
    """分页模式常量（字符串值，用于 GraphQL enum 或 resolver 比较）。

    刻意不使用 graphene.Enum，以保持本模块对 graphene 的依赖最小化。
    各模块在 schema 中定义自己的 graphene.Enum(PaginationMode) 并使用
    本常量作为值比较即可。
    """

    OFFSET = "OFFSET"
    KEYSET = "KEYSET"


def build_keyset_connection(
    items: List[Dict[str, Any]],
    total_count: int,
    first: Optional[int],
    after: Optional[str],
    sort_field: str = "updated_at",
    id_field: str = "id",
) -> Dict[str, Any]:
    """构造 keyset 模式的 Relay Connection 响应。

    与 build_connection 输出结构一致（edges/page_info/total_count），
    但 cursor 使用 keyset 格式 base64(json({v, id}))，用于稳定深翻页。

    要求 items 中每条记录都包含 sort_field 与 id_field 两个键。
    """
    page_size = first if first and first > 0 else DEFAULT_PAGE_SIZE

    edges: List[Dict[str, Any]] = []
    for item in items:
        cursor_payload = {
            "v": item.get(sort_field),
            "id": item.get(id_field),
        }
        edges.append(
            {
                "node": item,
                "cursor": encode_keyset_cursor(cursor_payload),
            }
        )

    has_next_page = len(items) >= page_size and total_count > len(items)
    page_info = {
        "has_next_page": has_next_page,
        "has_previous_page": bool(after),
        "start_cursor": edges[0]["cursor"] if edges else None,
        "end_cursor": edges[-1]["cursor"] if edges else None,
    }
    return {
        "edges": edges,
        "page_info": page_info,
        "total_count": total_count,
    }


# ---------------------------------------------------------------------------
# Keyset 谓词构造 + 类型还原 + LIMIT N+1 连接（v2 扩展，向后兼容）
# ---------------------------------------------------------------------------
# 以下为审查阶段发现的系统性缺陷的统一修复入口：
# - C5: cursor round-trip 类型丢失（DateTime -> str 隐式转换脆弱）
# - G14: keyset 谓词在多个 repository 重复手写
# - G2: keyset 模式仍跑 COUNT(*)，深翻页未真正优化
# 这些函数为 additive，既有 build_keyset_connection 保持不变。

import pendulum  # noqa: E402  (局部导入，避免未使用本特性的模块强依赖)


def restore_keyset_value(raw: Any, sort_type: Optional[str]) -> Any:
    """将 cursor 解码后的 ``v`` 还原为 SQL 可比较的强类型。

    Args:
        raw: ``decode_keyset_cursor`` 返回的 ``v``（json 反序列化后通常为
            str/number/None）。
        sort_type: 排序字段的类型标记，约定值：
            ``"datetime"`` -> pendulum.DateTime
            ``None`` / ``"str"`` / ``"int"`` -> 原样返回

    Returns:
        还原后的值。``raw`` 为 None 时直接返回 None（NULL 谓词由调用方处理）。
    """
    if raw is None or sort_type in (None, "str"):
        return raw
    if sort_type == "datetime":
        if isinstance(raw, str):
            try:
                return pendulum.parse(raw)
            except Exception:
                # 解析失败回退为原值，交由 driver 处理（保持旧行为，不引入新错误）
                return raw
        return raw
    if sort_type == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    return raw


def build_keyset_where_clause(
    sort_field: str,
    id_field: str,
    sort_dir: str,
    cursor_data: Optional[Dict[str, Any]],
    sort_type: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """构造 keyset 分页的 WHERE 谓词片段（不含前导 ``AND``，便于拼接到既有 where）。

    约定 ORDER BY 方向：DESC 取「小于游标」即新页，ASC 取「大于游标」。
    本函数仅返回谓词 SQL 片段（如 ``(created_at < :cv OR (created_at = :cv AND id < :cid))``），
    绑定参数写入 ``params``（若提供）。

    Args:
        sort_field: 排序列名（调用方须做白名单校验）。
        id_field: 唯一标识列名（组合键稳定排序用）。
        sort_dir: ``"DESC"`` 或 ``"ASC"``。
        cursor_data: ``decode_keyset_cursor`` 的返回值；None 或缺 ``v`` 时返回空串
            （即无 cursor，取首页），同时不写入 params。
        sort_type: 排序列类型标记，见 ``restore_keyset_value``。
        params: 若提供，则将 ``:cv`` / ``:cid`` 写入此 dict（原地修改并复用）；
            若为 None 则仅返回片段，调用方自行绑定。

    Returns:
        SQL 片段字符串。无 cursor 时返回 ``""``。
    """
    if not cursor_data or cursor_data.get("v") is None and cursor_data.get("id") is None:
        return ""
    cv = restore_keyset_value(cursor_data.get("v"), sort_type)
    cid = cursor_data.get("id")
    op = "<" if str(sort_dir).upper() == "DESC" else ">"
    clause = f"({sort_field} {op} :cv OR ({sort_field} = :cv AND {id_field} {op} :cid))"
    if params is not None:
        params["cv"] = cv
        params["cid"] = cid
    return clause


def build_keyset_connection_no_count(
    items: List[Dict[str, Any]],
    first: Optional[int],
    after: Optional[str],
    sort_field: str = "updated_at",
    id_field: str = "id",
    total_count: Optional[int] = None,
) -> Dict[str, Any]:
    """构造 keyset Connection，使用 LIMIT N+1 策略判定 ``has_next_page``。

    与 ``build_keyset_connection`` 的差异（G2 修复）：
    - 调用方应查询 ``LIMIT :page_size+1``，传入 ``items``（含多取的 1 条）；
    - ``has_next_page = len(items) > page_size``，若为 True 则截断末尾多取行；
    - ``total_count`` 可选：传入则填入响应（仍触发 COUNT，仅当客户端需要
      ``totalCount`` 时调用方才计算）；为 None 时响应 ``total_count`` 置 None。

    输出结构与 ``build_keyset_connection`` 一致。
    """
    page_size = first if first and first > 0 else DEFAULT_PAGE_SIZE
    has_next = len(items) > page_size
    page_items = items[:page_size] if has_next else items

    edges: List[Dict[str, Any]] = []
    for item in page_items:
        edges.append(
            {
                "node": item,
                "cursor": encode_keyset_cursor(
                    {"v": item.get(sort_field), "id": item.get(id_field)}
                ),
            }
        )
    page_info = {
        "has_next_page": has_next,
        "has_previous_page": bool(after),
        "start_cursor": edges[0]["cursor"] if edges else None,
        "end_cursor": edges[-1]["cursor"] if edges else None,
    }
    return {
        "edges": edges,
        "page_info": page_info,
        "total_count": total_count,
    }
