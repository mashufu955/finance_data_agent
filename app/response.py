"""Unified API response helpers."""

from __future__ import annotations

from typing import Any


def ok(data: Any = None) -> dict[str, Any]:
    return {"code": 0, "data": data}


def list_ok(items: list[Any], total_count: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"list": items}
    if total_count is not None:
        result["total_count"] = total_count
    return {"code": 0, "data": result}


def created(data: Any = None) -> dict[str, Any]:
    return {"code": 0, "data": data}
