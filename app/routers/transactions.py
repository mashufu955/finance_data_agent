"""Transaction processing endpoints."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Request, HTTPException, Query

from app.database import fetch_one, fetch_all, insert, execute
from app.response import ok, list_ok
from app.idempotency import check_idempotency, record_request
from app.utils import gen_no, serialize_row, serialize_list

router = APIRouter(tags=["transactions"])


def _idem(request: Request) -> tuple[str, str]:
    channel_code = request.headers.get("X-Channel-Code", "")
    operator_no = request.headers.get("X-Operator-No", "system")
    return channel_code, operator_no


# ---------------------------------------------------------------------------
# POST /api/v1/transactions
# ---------------------------------------------------------------------------
@router.post("/api/v1/transactions")
async def create_transaction(request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    customer_no = body.get("customer_no")
    account_no = body.get("account_no")
    transaction_type = body.get("transaction_type")
    amount = body.get("amount")
    currency_code = body.get("currency_code")
    related_type = body.get("related_type")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    customer = fetch_one("SELECT id FROM customer WHERE customer_no = %s", (customer_no,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    account = fetch_one(
        "SELECT id, balance_amount, available_amount, frozen_amount, open_channel_id "
        "FROM bank_account WHERE account_no = %s",
        (account_no,),
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]
    balance = float(account["balance_amount"])
    available = float(account["available_amount"])
    channel_id = account["open_channel_id"]

    transaction_no = gen_no("TXN")

    transaction_status = "success"
    if transaction_type in ["payment", "withdrawal"]:
        if available < float(amount):
            transaction_status = "failed"

    reconcile_status = "closed" if transaction_status == "success" else "pending"
    now = datetime.datetime.now()

    from_account_id = account_id if transaction_type in ("payment", "withdrawal") else None
    to_account_id = account_id if transaction_type == "deposit" else None

    txn_id = insert(
        """
        INSERT INTO account_transaction
            (transaction_no, customer_id, from_account_id, to_account_id,
             channel_id, transaction_type, transaction_status, reconcile_status,
             currency_code, transaction_amount, related_type,
             transaction_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (transaction_no, customer_id, from_account_id, to_account_id,
         channel_id, transaction_type, transaction_status, reconcile_status,
         currency_code, amount, related_type, now, now, now),
    )

    if transaction_status == "success":
        if transaction_type == "deposit":
            new_balance = balance + float(amount)
            new_available = available + float(amount)
        else:
            new_balance = balance - float(amount)
            new_available = available - float(amount)

        execute(
            "UPDATE bank_account SET balance_amount = %s, available_amount = %s, updated_at = %s WHERE id = %s",
            (new_balance, new_available, now, account_id),
        )

        ledger_no = gen_no("LDG")
        amount_delta = str(amount) if transaction_type == "deposit" else str(-float(amount))
        insert(
            """
            INSERT INTO account_ledger
                (ledger_no, account_id, customer_id, transaction_id, ledger_type,
                 currency_code, amount_delta, frozen_delta, balance_after,
                 frozen_after, available_after, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'0',%s,'0',%s,%s)
            """,
            (ledger_no, account_id, customer_id, txn_id, transaction_type,
             currency_code, amount_delta, str(new_balance), str(new_available), now),
        )

    channel_txn_no = gen_no("CHN")
    insert(
        """
        INSERT INTO channel_transaction
            (channel_txn_no, channel_id, transaction_id, request_no, request_type,
             request_status, callback_status, reconcile_status, currency_code,
             channel_amount, requested_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (channel_txn_no, channel_id, txn_id, request_no, transaction_type,
         transaction_status, transaction_status, reconcile_status, currency_code,
         amount, now, now, now),
    )

    txn_row = fetch_one("SELECT * FROM account_transaction WHERE id = %s", (txn_id,))
    response = ok(serialize_row(txn_row))
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# GET /api/v1/transactions/{transaction_no}
# ---------------------------------------------------------------------------
@router.get("/api/v1/transactions/{transaction_no}")
async def get_transaction(transaction_no: str):
    row = fetch_one(
        "SELECT * FROM account_transaction WHERE transaction_no = %s",
        (transaction_no,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return ok(serialize_row(row))


# ---------------------------------------------------------------------------
# GET /api/v1/accounts/{account_no}/transactions
# ---------------------------------------------------------------------------
@router.get("/api/v1/accounts/{account_no}/transactions")
async def list_account_transactions(
    account_no: str, page_size: int = Query(20, ge=1, le=100)
):
    account = fetch_one("SELECT id FROM bank_account WHERE account_no = %s", (account_no,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    count_row = fetch_one(
        "SELECT COUNT(*) AS total FROM account_transaction WHERE from_account_id = %s OR to_account_id = %s",
        (account["id"], account["id"]),
    )
    total_count = count_row["total"]

    rows = fetch_all(
        "SELECT * FROM account_transaction WHERE from_account_id = %s OR to_account_id = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (account["id"], account["id"], page_size),
    )
    return list_ok(serialize_list(rows), total_count=total_count)


# ---------------------------------------------------------------------------
# GET /api/v1/accounts/{account_no}/ledgers
# ---------------------------------------------------------------------------
@router.get("/api/v1/accounts/{account_no}/ledgers")
async def list_account_ledgers(
    account_no: str, page_size: int = Query(20, ge=1, le=100)
):
    account = fetch_one("SELECT id FROM bank_account WHERE account_no = %s", (account_no,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    count_row = fetch_one(
        "SELECT COUNT(*) AS total FROM account_ledger WHERE account_id = %s",
        (account["id"],),
    )
    total_count = count_row["total"]

    rows = fetch_all(
        "SELECT * FROM account_ledger WHERE account_id = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (account["id"], page_size),
    )
    return list_ok(serialize_list(rows), total_count=total_count)
