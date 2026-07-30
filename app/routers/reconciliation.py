"""Reconciliation and fund freeze endpoints."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Request, HTTPException

from app.database import fetch_one, insert, execute
from app.response import ok
from app.idempotency import check_idempotency, record_request
from app.utils import gen_no, resolve_employee_id, serialize_row

router = APIRouter(tags=["reconciliation"])


def _idem(request: Request) -> tuple[str, str]:
    channel_code = request.headers.get("X-Channel-Code", "")
    operator_no = request.headers.get("X-Operator-No", "system")
    return channel_code, operator_no


# ---------------------------------------------------------------------------
# POST /api/v1/fund-freezes
# ---------------------------------------------------------------------------
@router.post("/api/v1/fund-freezes")
async def create_fund_freeze(request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    account_no = body.get("account_no")
    freeze_amount = body.get("freeze_amount")
    freeze_type = body.get("freeze_type")
    freeze_reason = body.get("freeze_reason")
    related_type = body.get("related_type")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    account = fetch_one(
        "SELECT id, customer_id, currency_code, frozen_amount, available_amount "
        "FROM bank_account WHERE account_no = %s",
        (account_no,),
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account_id = account["id"]
    customer_id = account["customer_id"]
    currency_code = account["currency_code"]
    current_frozen = float(account["frozen_amount"])
    current_available = float(account["available_amount"])

    freeze_no = gen_no("FRZ")
    now = datetime.datetime.now()

    freeze_id = insert(
        """
        INSERT INTO fund_freeze
            (freeze_no, account_id, customer_id, freeze_type, related_type,
             currency_code, freeze_amount, released_amount, freeze_status,
             frozen_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,0,'frozen',%s,%s,%s)
        """,
        (freeze_no, account_id, customer_id, freeze_type, related_type,
         currency_code, freeze_amount, now, now, now),
    )

    new_frozen = current_frozen + float(freeze_amount)
    new_available = current_available - float(freeze_amount)
    execute(
        "UPDATE bank_account SET frozen_amount = %s, available_amount = %s, updated_at = %s WHERE id = %s",
        (new_frozen, new_available, now, account_id),
    )

    emp_id = resolve_employee_id(operator_no)
    operation_no = gen_no("FRZOP")
    insert(
        """
        INSERT INTO fund_freeze_operation
            (operation_no, freeze_id, account_id, customer_id, related_type,
             operation_type, currency_code, operation_amount, before_frozen_amount,
             after_frozen_amount, operator_id, operation_reason, operated_at, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (operation_no, freeze_id, account_id, customer_id, related_type,
         "freeze", currency_code, freeze_amount, current_frozen, new_frozen,
         emp_id, freeze_reason, now, now),
    )

    freeze_row = fetch_one("SELECT * FROM fund_freeze WHERE id = %s", (freeze_id,))
    response = ok(serialize_row(freeze_row))
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/fund-freezes/{freeze_no}/operations
# ---------------------------------------------------------------------------
@router.post("/api/v1/fund-freezes/{freeze_no}/operations")
async def create_freeze_operation(freeze_no: str, request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    operation_type = body.get("operation_type")
    amount = body.get("amount")
    reason = body.get("reason")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    freeze = fetch_one(
        "SELECT id, account_id, customer_id, currency_code, freeze_amount, "
        "released_amount, freeze_status, related_type FROM fund_freeze WHERE freeze_no = %s",
        (freeze_no,),
    )
    if not freeze:
        raise HTTPException(status_code=404, detail="Fund freeze not found")

    freeze_id = freeze["id"]
    account_id = freeze["account_id"]
    customer_id = freeze["customer_id"]
    currency_code = freeze["currency_code"]

    account = fetch_one(
        "SELECT frozen_amount, available_amount FROM bank_account WHERE id = %s",
        (account_id,),
    )
    current_frozen = float(account["frozen_amount"])
    current_available = float(account["available_amount"])

    emp_id = resolve_employee_id(operator_no)
    operation_no = gen_no("FRZOP")
    before_frozen = current_frozen
    after_frozen = current_frozen - float(amount)
    now = datetime.datetime.now()

    insert(
        """
        INSERT INTO fund_freeze_operation
            (operation_no, freeze_id, account_id, customer_id, related_type, operation_type,
             currency_code, operation_amount, before_frozen_amount, after_frozen_amount,
             operator_id, operation_reason, operated_at, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (operation_no, freeze_id, account_id, customer_id, freeze["related_type"], operation_type,
         currency_code, amount, before_frozen, after_frozen, emp_id, reason, now, now),
    )

    new_released = float(freeze["released_amount"]) + float(amount)
    execute(
        "UPDATE fund_freeze SET released_amount = %s, freeze_status = %s, released_at = %s, updated_at = %s WHERE id = %s",
        (new_released, "released", now, now, freeze_id),
    )

    new_frozen_bal = current_frozen - float(amount)
    new_available_bal = current_available + float(amount)
    execute(
        "UPDATE bank_account SET frozen_amount = %s, available_amount = %s, updated_at = %s WHERE id = %s",
        (new_frozen_bal, new_available_bal, now, account_id),
    )

    operation_row = fetch_one(
        "SELECT * FROM fund_freeze_operation WHERE freeze_id = %s ORDER BY id DESC LIMIT 1",
        (freeze_id,),
    )
    result = serialize_row(operation_row)
    result["freeze_status"] = "released"
    response = ok(result)
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/reconciliation/batches
# ---------------------------------------------------------------------------
@router.post("/api/v1/reconciliation/batches")
async def create_reconciliation_batch(request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    channel_code = body.get("channel_code")
    reconcile_date = body.get("reconcile_date")

    idem_channel, idem_operator = _idem(request)
    existing = check_idempotency(request_no, idem_channel, idem_operator, body)
    if existing is not None:
        return ok(existing)

    channel = fetch_one("SELECT id FROM dim_channel WHERE channel_code = %s", (channel_code,))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel_id = channel["id"]

    batch_no = gen_no("BATCH")
    now = datetime.datetime.now()

    batch_id = insert(
        """
        INSERT INTO reconciliation_batch
            (batch_no, channel_id, reconcile_date, file_name, batch_status,
             started_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,'created',%s,%s,%s)
        """,
        (batch_no, channel_id, reconcile_date, f"{batch_no}.csv", now, now, now),
    )

    batch_row = fetch_one("SELECT * FROM reconciliation_batch WHERE id = %s", (batch_id,))
    response = ok(serialize_row(batch_row))
    record_request(request_no, idem_channel, idem_operator, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/reconciliation/results
# ---------------------------------------------------------------------------
@router.post("/api/v1/reconciliation/results")
async def create_reconciliation_result(request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    batch_no = body.get("batch_no")
    transaction_no = body.get("transaction_no")
    result_type = body.get("result_type")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    batch = fetch_one("SELECT id FROM reconciliation_batch WHERE batch_no = %s", (batch_no,))
    if not batch:
        raise HTTPException(status_code=404, detail="Reconciliation batch not found")
    batch_id = batch["id"]

    transaction = fetch_one("SELECT id FROM account_transaction WHERE transaction_no = %s", (transaction_no,))
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    transaction_id = transaction["id"]

    result_no = gen_no("RES")
    now = datetime.datetime.now()

    result_id = insert(
        """
        INSERT INTO reconciliation_result
            (result_no, batch_id, transaction_id, result_type,
             difference_amount, process_status, created_at, updated_at)
        VALUES (%s,%s,%s,%s,0,'pending',%s,%s)
        """,
        (result_no, batch_id, transaction_id, result_type, now, now),
    )

    result_row = fetch_one("SELECT * FROM reconciliation_result WHERE id = %s", (result_id,))
    response = ok(serialize_row(result_row))
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/reconciliation/adjustments
# ---------------------------------------------------------------------------
@router.post("/api/v1/reconciliation/adjustments")
async def create_reconciliation_adjustment(request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    result_no = body.get("result_no")
    adjustment_amount = body.get("adjustment_amount")
    adjustment_reason = body.get("adjustment_reason")
    adjustment_direction = body.get("adjustment_direction")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    result = fetch_one(
        "SELECT id, transaction_id FROM reconciliation_result WHERE result_no = %s",
        (result_no,),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Reconciliation result not found")
    result_id = result["id"]
    transaction_id = result["transaction_id"]

    transaction = fetch_one("SELECT currency_code FROM account_transaction WHERE id = %s", (transaction_id,))
    currency_code = transaction["currency_code"] if transaction else "CNY"

    adjustment_no = gen_no("ADJ")
    now = datetime.datetime.now()

    adjustment_id = insert(
        """
        INSERT INTO reconciliation_adjustment
            (adjustment_no, result_id, transaction_id, currency_code, adjustment_amount,
             adjustment_direction, adjustment_status, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s)
        """,
        (adjustment_no, result_id, transaction_id, currency_code, adjustment_amount,
         adjustment_direction, now, now),
    )

    adjustment_row = fetch_one("SELECT * FROM reconciliation_adjustment WHERE id = %s", (adjustment_id,))
    response = ok(serialize_row(adjustment_row))
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/reconciliation/adjustments/{adjustment_no}/approval
# ---------------------------------------------------------------------------
@router.post("/api/v1/reconciliation/adjustments/{adjustment_no}/approval")
async def approve_reconciliation_adjustment(adjustment_no: str, request: Request):
    body = await request.json()
    request_no = body.get("request_no")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    adjustment = fetch_one(
        "SELECT id FROM reconciliation_adjustment WHERE adjustment_no = %s",
        (adjustment_no,),
    )
    if not adjustment:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    adjustment_id = adjustment["id"]

    emp_id = resolve_employee_id(operator_no)
    now = datetime.datetime.now()
    execute(
        "UPDATE reconciliation_adjustment SET adjustment_status = %s, "
        "approved_by = %s, approved_at = %s, updated_at = %s WHERE id = %s",
        ("approved", emp_id, now, now, adjustment_id),
    )

    response = ok({"adjustment_status": "approved"})
    record_request(request_no, channel_code, operator_no, body, response)
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/reconciliation/adjustments/{adjustment_no}/post
# ---------------------------------------------------------------------------
@router.post("/api/v1/reconciliation/adjustments/{adjustment_no}/post")
async def post_reconciliation_adjustment(adjustment_no: str, request: Request):
    body = await request.json()
    request_no = body.get("request_no")
    account_no = body.get("account_no")
    post_amount = body.get("post_amount")

    channel_code, operator_no = _idem(request)
    existing = check_idempotency(request_no, channel_code, operator_no, body)
    if existing is not None:
        return ok(existing)

    adjustment = fetch_one(
        "SELECT id, adjustment_direction FROM reconciliation_adjustment WHERE adjustment_no = %s",
        (adjustment_no,),
    )
    if not adjustment:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    adjustment_id = adjustment["id"]
    adjustment_direction = adjustment["adjustment_direction"]

    account = fetch_one(
        "SELECT id, balance_amount, available_amount FROM bank_account WHERE account_no = %s",
        (account_no,),
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]
    current_balance = float(account["balance_amount"])
    current_available = float(account["available_amount"])

    now = datetime.datetime.now()
    execute(
        "UPDATE reconciliation_adjustment SET adjustment_status = %s, posted_at = %s, updated_at = %s WHERE id = %s",
        ("posted", now, now, adjustment_id),
    )

    if adjustment_direction == "credit":
        new_balance = current_balance + float(post_amount)
        new_available = current_available + float(post_amount)
    else:
        new_balance = current_balance - float(post_amount)
        new_available = current_available - float(post_amount)

    execute(
        "UPDATE bank_account SET balance_amount = %s, available_amount = %s, updated_at = %s WHERE id = %s",
        (new_balance, new_available, now, account_id),
    )

    response = ok({"adjustment_status": "posted"})
    record_request(request_no, channel_code, operator_no, body, response)
    return response
