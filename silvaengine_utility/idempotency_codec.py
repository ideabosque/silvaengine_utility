"""Lossless temporal values in cached mutation results, with legacy reads."""

from datetime import date, datetime
from typing import Any

FORMAT = "silvaengine.idempotency.temporal.v1"


def encode_result(value: Any) -> Any:
    found = False

    def encode(item: Any) -> Any:
        nonlocal found
        if isinstance(item, datetime):
            found = True
            return {"__temporal__": "datetime", "iso": item.isoformat()}
        if isinstance(item, date):
            found = True
            return {"__temporal__": "date", "iso": item.isoformat()}
        if isinstance(item, dict):
            return {key: encode(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [encode(val) for val in item]
        return item

    encoded = encode(value)
    return {"__format__": FORMAT, "value": encoded} if found else value


def decode_result(value: Any) -> Any:
    typed = (
        isinstance(value, dict)
        and value.get("__format__") == FORMAT
        and set(value) == {"__format__", "value"}
    )

    def decode(item: Any, field: str = "") -> Any:
        if isinstance(item, dict):
            if typed and set(item) == {"__temporal__", "iso"}:
                if item["__temporal__"] == "datetime":
                    return datetime.fromisoformat(item["iso"])
                if item["__temporal__"] == "date":
                    return date.fromisoformat(item["iso"])
            return {key: decode(val, str(key)) for key, val in item.items()}
        if isinstance(item, list):
            return [decode(val) for val in item]
        # Legacy caches used default=str. Only schema-style timestamp fields
        # are restored; ordinary text and arbitrary date-looking strings stay text.
        if (
            not typed
            and isinstance(item, str)
            and (field.endswith("_at") or field.endswith("At"))
        ):
            try:
                if "T" in item or " " in item:
                    return datetime.fromisoformat(item.replace("Z", "+00:00"))
            except ValueError:
                pass
        return item

    return decode(value["value"] if typed else value)
