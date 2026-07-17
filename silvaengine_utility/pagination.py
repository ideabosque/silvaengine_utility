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
