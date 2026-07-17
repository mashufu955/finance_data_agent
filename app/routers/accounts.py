"""Account management endpoints."""

from __future__ import annotations

import datetime
import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Query

from app.database import fetch_one, fetch_all, insert, execute
from app.response import ok, list_ok
from app.idempotency import check_idempotency, record_request

router = APIRouter(tags=["accounts"])


def gen_no(prefix: str) -> str:
    return f"{prefix}{int(time.time() * 1000000)}"


def _ser(v: Any) -> Any:
    if isinstance(v, (Decimal, datetime.datetime, datetime.date)):
        return str(v)
    return v


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _ser(v) for k, v in row.items()}


def _serialize_list(rows: list[dict]) -> list[dict]:
    return [_serialize_row(r) for r in rows]


def _idem(request: Request) -> tuple[str, str, str]:
    channel_code = request.headers.get("X-Channel-Code", "")
    operator_no = request.headers.get("X-Operator-No", "system")
    return channel_code, operator_no


def _resolve_employee_id(employee_no: str) -> int | None:
    if not employee_no:
        return None
    row = fetch_one("SELECT id FROM dim_employee WHERE employee_no = %s", (employee_no,))
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# POST /api/v1/accounts
# ---------------------------------------------------------------------------
@router.post("/api/v1/accounts")
async def create_account(request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    customer_no = body.get("customer_no")
    product_code = body.get("product_code")
    currency_code = body.get("currency_code")
    branch_code = body.get("branch_code")
    open_amount = body.get("open_amount", "0")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    customer = fetch_one("SELECT id FROM customer WHERE customer_no = %s", (customer_no,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    product = fetch_one("SELECT id FROM account_product WHERE product_code = %s", (product_code,))
    if not product:
        raise HTTPException(status_code=404, detail="Account product not found")
    account_product_id = product["id"]

    branch = fetch_one("SELECT id FROM dim_branch WHERE branch_code = %s", (branch_code,))
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    branch_id = branch["id"]

    channel_code_header = request.headers.get("X-Channel-Code", "")
    channel = fetch_one("SELECT id FROM dim_channel WHERE channel_code = %s", (channel_code_header,))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    open_channel_id = channel["id"]

    account_no = gen_no("ACC")
    now = datetime.datetime.now()

    account_id = insert(
        """
        INSERT INTO bank_account
            (account_no, customer_id, branch_id, open_channel_id, account_product_id,
             currency_code, account_type, account_status, balance_amount,
             frozen_amount, available_amount, opened_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,'personal','active',%s,0,%s,%s,%s,%s)
        """,
        (account_no, customer_id, branch_id, open_channel_id, account_product_id,
         currency_code, open_amount, open_amount, now, now, now),
    )

    ledger_no = gen_no("LDG")
    insert(
        """
        INSERT INTO account_ledger
            (ledger_no, account_id, customer_id, ledger_type, currency_code,
             amount_delta, frozen_delta, balance_after, frozen_after, available_after, created_at)
        VALUES (%s,%s,%s,'opening',%s,%s,'0',%s,'0',%s,%s)
        """,
        (ledger_no, account_id, customer_id, currency_code,
         str(open_amount), str(open_amount), str(open_amount), now),
    )

    emp_id = _resolve_employee_id(operator_no)
    insert(
        """
        INSERT INTO bank_account_status_history
            (account_id, customer_id, change_seq, from_status, to_status,
             change_reason, related_type, operator_id, changed_at, created_at)
        VALUES (%s,%s,1,'none','active','account_opening','account',%s,%s,%s)
        """,
        (account_id, customer_id, emp_id, now, now),
    )

    response = ok({"account_no": account_no})
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# GET /api/v1/accounts/{account_no}
# ---------------------------------------------------------------------------
@router.get("/api/v1/accounts/{account_no}")
async def get_account(account_no: str):
    row = fetch_one("SELECT * FROM bank_account WHERE account_no = %s", (account_no,))
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return ok(_serialize_row(row))


# ---------------------------------------------------------------------------
# POST /api/v1/accounts/{account_no}/cards
# ---------------------------------------------------------------------------
@router.post("/api/v1/accounts/{account_no}/cards")
async def create_card(account_no: str, request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    card_type = body.get("card_type")
    card_level = body.get("card_level")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    account = fetch_one("SELECT id, customer_id FROM bank_account WHERE account_no = %s", (account_no,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    card_no = gen_no("CRD")
    now = datetime.datetime.now()
    card_id = insert(
        """
        INSERT INTO bank_card
            (card_no, customer_id, account_id, card_type, card_level, card_status,
             issued_at, expired_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,'active',%s,DATE_ADD(%s, INTERVAL 5 YEAR),%s,%s)
        """,
        (card_no, account["customer_id"], account["id"], card_type, card_level,
         now, now, now, now),
    )

    card_row = fetch_one("SELECT * FROM bank_card WHERE id = %s", (card_id,))
    response = ok(_serialize_row(card_row))
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/accounts/{account_no}/status-changes
# ---------------------------------------------------------------------------
@router.post("/api/v1/accounts/{account_no}/status-changes")
async def change_account_status(account_no: str, request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    target_status = body.get("target_status")
    reason = body.get("reason")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    account = fetch_one(
        "SELECT id, customer_id, account_status FROM bank_account WHERE account_no = %s",
        (account_no,),
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    seq_row = fetch_one(
        "SELECT COALESCE(MAX(change_seq), 0) AS max_seq FROM bank_account_status_history WHERE account_id = %s",
        (account["id"],),
    )
    change_seq = (seq_row["max_seq"] or 0) + 1

    emp_id = _resolve_employee_id(operator_no)
    now = datetime.datetime.now()

    insert(
        """
        INSERT INTO bank_account_status_history
            (account_id, customer_id, change_seq, from_status, to_status,
             change_reason, related_type, operator_id, changed_at, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,'account',%s,%s,%s)
        """,
        (account["id"], account["customer_id"], change_seq,
         account["account_status"], target_status, reason, emp_id, now, now),
    )

    execute(
        "UPDATE bank_account SET account_status = %s, updated_at = %s WHERE id = %s",
        (target_status, now, account["id"]),
    )

    response = ok({"current_status": target_status})
    record_request(request_no, channel_code, operator_no, body, response)
    return response
