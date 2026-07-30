"""Shared utility functions used across API routers."""

from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.database import fetch_one


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_value(v: Any) -> Any:
    """Convert a single value to JSON-safe type."""
    if isinstance(v, (Decimal, datetime, date)):
        return str(v)
    return v


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert all values in a dict row to JSON-safe types."""
    return {k: serialize_value(v) for k, v in row.items()}


def serialize_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a list of dict rows to JSON-safe types."""
    return [serialize_row(r) for r in rows]


def serialize_deep(data: Any) -> Any:
    """Recursively convert datetime/date/Decimal in nested structures."""
    if isinstance(data, list):
        for item in data:
            serialize_deep(item)
        return data
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (datetime, date, Decimal)):
                data[key] = str(value)
            elif isinstance(value, (list, dict)):
                serialize_deep(value)
        return data
    return data


# ---------------------------------------------------------------------------
# ID / No generation
# ---------------------------------------------------------------------------

def gen_no(prefix: str) -> str:
    """Generate a unique business number with the given prefix."""
    return f"{prefix}{int(time.time() * 1000000)}"


# ---------------------------------------------------------------------------
# Common lookups
# ---------------------------------------------------------------------------

def resolve_employee_id(employee_no: str) -> int | None:
    """Resolve employee number to dim_employee.id."""
    if not employee_no:
        return None
    row = fetch_one("SELECT id FROM dim_employee WHERE employee_no = %s", (employee_no,))
    return row["id"] if row else None
