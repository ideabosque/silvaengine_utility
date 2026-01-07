from graphene import Int, Argument, List, String, InputObjectType
from graphene.relay import ConnectionField, Connection
from sqlalchemy import asc, desc, and_, or_
from sqlalchemy.sql.sqltypes import DateTime
from datetime import datetime
import base64, json

from .graphql import JSON

class SortInput(InputObjectType):
    field = String()
    direction = String()

# ---------------- Base Connection ----------------
class BaseConnection(Connection):
    total_count = Int()
    total_page = Int(description="Total pages, only valid for offset/limit pagination")
    page_limit = Int(description="Limit for offset/limit pagination")

    class Meta:
        abstract = True  # <-- Important, tells Graphene this class is abstract

    def resolve_total_count(root, info):
        return getattr(root, "total_count", None)

    def resolve_total_page(root, info):
        limit = getattr(root, "page_limit", None)
        total_count = getattr(root, "total_count", None)
        if limit and total_count is not None:
            return (total_count + limit - 1) // limit
        return None
    
    def resolve_page_limit(root, info):
        return getattr(root, "page_limit", None)
    

class SQLAlchemyRelayConnectionField(ConnectionField):
    model = None
    default_order_by = None   # e.g. [("created_at", "DESC")]
    allowed_filter_fields = None
    cursor_fields = None

    def __init__(self, type_, *args, **kwargs):
        # Add default arguments if not already passed
        if "filters" not in kwargs:
            kwargs["filters"] = Argument(JSON)
        if "sort" not in kwargs:
            kwargs["sort"] = Argument(List(SortInput))
        if "limit" not in kwargs:
            kwargs["limit"] = Argument(Int)
        if "curpage" not in kwargs:
            kwargs["curpage"] = Argument(Int)

        super().__init__(type_, *args, **kwargs)

    @staticmethod
    def encode_cursor(data: dict | None) -> str | None:
        if not data:
            return None
        return base64.b64encode(json.dumps(data, default=str).encode()).decode()

    @staticmethod
    def decode_cursor(cursor: str | None) -> dict | None:
        if not cursor:
            return None
        return json.loads(base64.b64decode(cursor).decode())

    # -------- Keyset Pagination --------
    @classmethod
    def apply_keyset(cls, query, cursor_data, order_by, reverse=False):
        conditions = []
        for i, (field, direction) in enumerate(order_by):
            left = getattr(cls.model, field)
            value = cursor_data[field]

            dir_lower = direction.lower()
            if reverse:
                dir_lower = "desc" if dir_lower == "asc" else "asc"

            op = left < value if dir_lower == "desc" else left > value
            prefix = [getattr(cls.model, f) == cursor_data[f] for f, _ in order_by[:i]]
            conditions.append(and_(*prefix, op))

        return query.filter(or_(*conditions))

    # -------- Offset Pagination --------
    @classmethod
    def normalize_offset(cls, limit, curpage):
        limit = min(limit or 20, 100)
        curpage = max(curpage or 1, 1)
        return limit, (curpage - 1) * limit

    @classmethod
    def offset_to_cursor(cls, query, offset, order_by):
        if offset <= 0:
            return None
        row = (
            query
            .order_by(*[
                getattr(cls.model, f).desc() if d.lower() == "desc" else getattr(cls.model, f)
                for f, d in order_by
            ])
            .offset(offset - 1)
            .limit(1)
            .one_or_none()
        )
        if not row:
            return None
        return cls.encode_cursor({f: getattr(row, f) for f, _ in order_by})

    # -------- Filters --------
    OPERATORS = {
        "eq": lambda col, v: col == v,
        "ne": lambda col, v: col != v,
        "gt": lambda col, v: col > v,
        "gte": lambda col, v: col >= v,
        "lt": lambda col, v: col < v,
        "lte": lambda col, v: col <= v,
        "in": lambda col, v: col.in_(v),
        "ilike": lambda col, v: col.ilike(f"%{v}%"),
        "isnull": lambda col, v: col.is_(None) if v else col.is_not(None),
    }

    @classmethod
    def coerce_value(cls, column, value):
        if isinstance(column.type, DateTime) and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    @classmethod
    def apply_filters(cls, query, filters: dict):
        if not filters:
            return query

        conditions = []
        for field, ops in filters.items():
            if cls.allowed_filter_fields and field not in cls.allowed_filter_fields:
                continue
            column = getattr(cls.model, field, None)
            if not column:
                continue
            for op, value in ops.items():
                handler = cls.OPERATORS.get(op)
                if not handler:
                    continue
                value = cls.coerce_value(column, value)
                conditions.append(handler(column, value))

        if conditions:
            query = query.filter(and_(*conditions))
        return query

    # -------- Sort --------
    @classmethod
    def apply_sort(cls, query, sort):
        if sort:
            for s in sort:
                field = s.get("field")
                direction = s.get("direction", "ASC")
                column = getattr(cls.model, field, None)
                if not column:
                    continue
                query = query.order_by(desc(column) if direction.upper() == "DESC" else asc(column))
            return query
        if cls.default_order_by:
            for field, direction in cls.default_order_by:
                column = getattr(cls.model, field, None)
                if column:
                    query = query.order_by(desc(column) if direction.upper() == "DESC" else asc(column))
        return query

    # -------- Resolve --------
    @classmethod
    def resolve_connection(cls, connection_type, args, resolved):
        if resolved is None:
            return None
        if not hasattr(resolved, "count"):
            raise TypeError("Resolver must return a SQLAlchemy Query")

        query = resolved
        # filters
        query = cls.apply_filters(query, args.get("filters"))

        # sort
        query = cls.apply_sort(query, args.get("sort"))
        order_by = cls.default_order_by or []

        # total_count
        total_count = query.count()
        # pagination
        first = args.get("first")
        last = args.get("last")
        after = args.get("after")
        before = args.get("before")
        limit = args.get("limit")
        curpage = args.get("curpage")

        if first and limit:
            raise Exception("Cannot use Relay and limit pagination together")

        if limit:
            limit, offset = cls.normalize_offset(limit, curpage)
            first = limit
            after = cls.offset_to_cursor(query, offset, order_by)

        cursor_fields = cls.cursor_fields or [f for f, _ in order_by]

        if after:
            query = cls.apply_keyset(query, cls.decode_cursor(after),
                                     [(f, d) for f, d in order_by if f in cursor_fields])
        elif before:
            query = cls.apply_keyset(query, cls.decode_cursor(before),
                                     [(f, d) for f, d in order_by if f in cursor_fields],
                                     reverse=True)

        page_limit = first or last or 20
        rows = query.limit(page_limit + 1).all()
        has_extra = len(rows) > page_limit
        if last:
            rows = list(reversed(rows[:last]))
        else:
            rows = rows[:first]

        edges = []
        for i, row in enumerate(rows):
            cursor_data = {f: getattr(row, f) for f in cursor_fields}
            edges.append(
                {
                    "node": row,
                    "cursor":cls.encode_cursor(cursor_data)
                }
            )
        
        # page_info
        if first or limit:
            has_next_page = has_extra
            has_previous_page = bool(after)
        elif last:
            has_next_page = bool(before)
            has_previous_page = has_extra
        else:
            has_next_page = has_previous_page = False

        page_info = {
            "has_next_page": has_next_page,
            "has_previous_page": has_previous_page,
            "start_cursor": edges[0]["cursor"] if edges else None,
            "end_cursor": edges[-1]["cursor"] if edges else None,
        }
        return connection_type(
            edges=edges,
            total_count=total_count,
            total_page=(total_count + page_limit - 1) // page_limit if limit else None,
            page_limit=page_limit,
            page_info=page_info,
        )
