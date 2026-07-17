"""Idempotency support for API requests."""

from __future__ import annotations

from typing import Any

_RECORDS: dict[tuple[str, str, str], dict[str, Any]] = {}


def check_idempotency(request_no: str, channel_code: str, operator_no: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Check idempotency. Returns existing response if duplicate, raises on mismatch."""
    key = (request_no, channel_code, operator_no)
    if key in _RECORDS:
        existing = _RECORDS[key]
        if existing["payload"] == payload:
            return existing["response"]
        raise IdempotencyMismatchError(request_no)
    return None


def record_request(request_no: str, channel_code: str, operator_no: str, payload: dict[str, Any], response: dict[str, Any]) -> None:
    key = (request_no, channel_code, operator_no)
    _RECORDS[key] = {"payload": payload, "response": response}


class IdempotencyMismatchError(Exception):
    def __init__(self, request_no: str):
        self.request_no = request_no
        super().__init__(f"Idempotency payload mismatch for {request_no}")
