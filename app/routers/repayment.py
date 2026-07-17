"""Repayment, overdue, and fee-reduction endpoints."""

from __future__ import annotations

import datetime
import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(tags=["repayment"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_no_seq = 0


def gen_no(prefix: str) -> str:
    global _no_seq
    _no_seq += 1
    return f"{prefix}{int(time.time() * 1000000)}{_no_seq:04d}"


def _ser(obj: Any) -> Any:
    """Recursively convert Decimal / datetime values for JSON safety."""
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ser(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return str(obj)
    return obj


def _idem_key(request: Request, body: dict):
    """Extract idempotency parameters from headers + body."""
    return (
        body.get("request_no", ""),
        request.headers.get("X-Channel-Code", ""),
        request.headers.get("X-Operator-No", ""),
    )


# In-memory store for repayment records (no dedicated DDL table).
_repayment_records: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# 1. POST /api/v1/repayment/bills/generate
# ---------------------------------------------------------------------------

@router.post("/api/v1/repayment/bills/generate")
async def generate_repayment_bills(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    contract_no = body["contract_no"]
    bill_date = body.get("bill_date")
    period_start = body.get("period_start")
    period_end = body.get("period_end")

    # -- look up contract --
    contract = fetch_one(
        "SELECT id, customer_id, currency_code FROM loan_contract WHERE contract_no = %s", (contract_no,)
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Loan contract not found")
    contract_id = contract["id"]
    customer_id = contract["customer_id"]
    currency_code = contract["currency_code"]

    # -- look up schedules --
    schedules = fetch_all(
        "SELECT * FROM repayment_schedule WHERE contract_id = %s "
        "AND period_no >= %s AND period_no <= %s ORDER BY period_no",
        (contract_id, period_start, period_end),
    )

    now = datetime.datetime.now()
    bill_count = 0
    for sch in schedules:
        bill_no = gen_no("BL")
        total_amount = sch.get("total_amount") or 0
        principal_amount = sch.get("principal_amount") or 0
        interest_amount = sch.get("interest_amount") or 0
        insert(
            "INSERT INTO repayment_bill "
            "(bill_no, contract_id, schedule_id, customer_id, period_no, due_date, "
            "currency_code, principal_amount, interest_amount, fee_amount, penalty_amount, "
            "reduced_amount, paid_amount, written_off_amount, restructured_amount, "
            "outstanding_amount, bill_status, billed_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, 0, 0, %s, %s, %s, %s, %s)",
            (
                bill_no,
                contract_id,
                sch["id"],
                customer_id,
                sch["period_no"],
                sch.get("due_date"),
                currency_code,
                principal_amount,
                interest_amount,
                total_amount,
                "billed",
                now, now, now,
            ),
        )
        bill_count += 1

    result = {"bill_count": bill_count}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 2. GET /api/v1/repayment/bills
# ---------------------------------------------------------------------------

@router.get("/api/v1/repayment/bills")
def list_repayment_bills(contract_no: str = Query(None)):
    if contract_no:
        contract = fetch_one(
            "SELECT id FROM loan_contract WHERE contract_no = %s", (contract_no,)
        )
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        rows = fetch_all(
            "SELECT * FROM repayment_bill WHERE contract_id = %s ORDER BY period_no",
            (contract["id"],),
        )
    else:
        rows = fetch_all("SELECT * FROM repayment_bill ORDER BY period_no")
    return list_ok(_ser(rows), total_count=len(rows))


# ---------------------------------------------------------------------------
# 3. POST /api/v1/repayment/authorizations
# ---------------------------------------------------------------------------

@router.post("/api/v1/repayment/authorizations")
async def create_repayment_authorization(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    customer_no = body["customer_no"]
    contract_no = body.get("contract_no")
    account_no = body["account_no"]
    authorization_type = body.get("authorization_type")
    valid_from = body.get("valid_from")
    valid_to = body.get("valid_to")

    # -- look-ups --
    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s", (customer_no,)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    contract_id = None
    if contract_no:
        contract = fetch_one(
            "SELECT id FROM loan_contract WHERE contract_no = %s", (contract_no,)
        )
        if contract:
            contract_id = contract["id"]

    account = fetch_one(
        "SELECT id FROM bank_account WHERE account_no = %s", (account_no,)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]

    authorization_no = gen_no("RA")
    now = datetime.datetime.now()

    insert(
        "INSERT INTO repayment_authorization "
        "(authorization_no, contract_id, customer_id, account_id, "
        "authorization_type, authorization_status, valid_from, valid_to, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            authorization_no, contract_id, customer_id, account_id,
            authorization_type, "active", valid_from, valid_to, now, now,
        ),
    )

    result = {"authorization_status": "active"}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 4. POST /api/v1/repayments
# ---------------------------------------------------------------------------

@router.post("/api/v1/repayments")
async def make_repayment(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    bill_no = body["bill_no"]
    account_no = body["account_no"]
    repayment_amount = Decimal(str(body["repayment_amount"]))
    repayment_type = body.get("repayment_type")

    # -- look up bill --
    bill = fetch_one(
        "SELECT * FROM repayment_bill WHERE bill_no = %s", (bill_no,)
    )
    if not bill:
        raise HTTPException(status_code=404, detail="Repayment bill not found")
    customer_id = bill["customer_id"]
    currency_code = bill["currency_code"]

    # -- look up account --
    account = fetch_one(
        "SELECT id, open_channel_id FROM bank_account WHERE account_no = %s", (account_no,)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]
    channel_id = account["open_channel_id"]

    repayment_no = gen_no("RPM")

    # -- update bill --
    new_paid = Decimal(str(bill.get("paid_amount") or 0)) + repayment_amount
    new_outstanding = Decimal(str(bill.get("outstanding_amount") or 0)) - repayment_amount
    if new_outstanding <= 0:
        new_outstanding = 0
        execute(
            "UPDATE repayment_bill SET paid_amount = %s, outstanding_amount = %s, "
            "bill_status = %s, paid_at = NOW() WHERE id = %s",
            (new_paid, new_outstanding, "settled", bill["id"]),
        )
    else:
        execute(
            "UPDATE repayment_bill SET paid_amount = %s, outstanding_amount = %s "
            "WHERE id = %s",
            (new_paid, new_outstanding, bill["id"]),
        )

    # -- account transaction (debit) --
    txn_no = gen_no("TXN")
    now = datetime.datetime.now()
    insert(
        "INSERT INTO account_transaction "
        "(transaction_no, customer_id, from_account_id, channel_id, transaction_type, "
        "transaction_status, reconcile_status, currency_code, transaction_amount, "
        "related_type, transaction_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (txn_no, customer_id, account_id, channel_id, "payment",
         "success", "pending", currency_code, repayment_amount,
         "loan_repayment", now, now, now),
    )

    # -- store repayment record in memory --
    _repayment_records[repayment_no] = {
        "repayment_no": repayment_no,
        "bill_no": bill_no,
        "account_no": account_no,
        "repayment_amount": float(repayment_amount),
        "repayment_type": repayment_type,
        "repayment_status": "success",
    }

    result = {"repayment_status": "success", "repayment_no": repayment_no}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 5. GET /api/v1/repayments/{repayment_no}
# ---------------------------------------------------------------------------

@router.get("/api/v1/repayments/{repayment_no}")
def get_repayment(repayment_no: str):
    record = _repayment_records.get(repayment_no)
    if not record:
        raise HTTPException(status_code=404, detail="Repayment record not found")
    return ok(record)


# ---------------------------------------------------------------------------
# 6. GET /api/v1/overdues
# ---------------------------------------------------------------------------

@router.get("/api/v1/overdues")
def list_overdues(contract_no: str = Query(None)):
    if contract_no:
        contract = fetch_one(
            "SELECT id FROM loan_contract WHERE contract_no = %s", (contract_no,)
        )
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        rows = fetch_all(
            "SELECT * FROM overdue_record WHERE contract_id = %s",
            (contract["id"],),
        )
    else:
        rows = fetch_all("SELECT * FROM overdue_record")
    return list_ok(_ser(rows), total_count=len(rows))


# ---------------------------------------------------------------------------
# 7. POST /api/v1/overdues/refresh
# ---------------------------------------------------------------------------

@router.post("/api/v1/overdues/refresh")
async def refresh_overdues(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    contract_no = body["contract_no"]
    overdue_date = body["overdue_date"]

    # Look up contract
    contract = fetch_one(
        "SELECT id, customer_id, currency_code FROM loan_contract WHERE contract_no = %s",
        (contract_no,),
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract_id = contract["id"]
    customer_id = contract["customer_id"]
    currency_code = contract["currency_code"]

    # Parse overdue_date for day calculation
    if isinstance(overdue_date, str):
        od_dt = datetime.datetime.strptime(overdue_date, "%Y-%m-%d")
    else:
        od_dt = overdue_date

    # -- find overdue bills --
    bills = fetch_all(
        "SELECT * FROM repayment_bill "
        "WHERE contract_id = %s AND due_date < %s "
        "AND outstanding_amount > 0 AND bill_status != %s",
        (contract_id, overdue_date, "settled"),
    )

    overdue_count = 0
    for bill in bills:
        due_dt = bill["due_date"]
        if isinstance(due_dt, datetime.date) and not isinstance(due_dt, datetime.datetime):
            due_dt = datetime.datetime.combine(due_dt, datetime.time.min)
        elif isinstance(due_dt, str):
            due_dt = datetime.datetime.strptime(due_dt, "%Y-%m-%d")
        overdue_days = (od_dt - due_dt).days

        existing = fetch_one(
            "SELECT id FROM overdue_record WHERE bill_id = %s",
            (bill["id"],),
        )
        now = datetime.datetime.now()
        if existing:
            execute(
                "UPDATE overdue_record SET overdue_days = %s, "
                "overdue_total_amount = %s, updated_at = %s WHERE id = %s",
                (overdue_days, bill["outstanding_amount"], now, existing["id"]),
            )
        else:
            overdue_no = gen_no("ODR")
            insert(
                "INSERT INTO overdue_record "
                "(overdue_no, bill_id, contract_id, customer_id, period_no, "
                "overdue_start_date, overdue_days, currency_code, "
                "overdue_principal_amount, overdue_interest_amount, overdue_fee_amount, "
                "penalty_amount, overdue_total_amount, paid_amount, reduced_amount, "
                "written_off_amount, restructured_amount, recovered_amount, "
                "outstanding_amount, overdue_level, overdue_status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, 0, 0, 0, 0, 0, %s, %s, %s, %s, %s)",
                (
                    overdue_no,
                    bill["id"],
                    contract_id,
                    customer_id,
                    bill["period_no"],
                    overdue_date,
                    overdue_days,
                    currency_code,
                    bill["outstanding_amount"],
                    bill["outstanding_amount"],
                    bill["outstanding_amount"],
                    "normal",
                    "overdue",
                    now, now,
                ),
            )
        overdue_count += 1

    result = {"overdue_count": overdue_count}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 8. POST /api/v1/fee-reductions
# ---------------------------------------------------------------------------

@router.post("/api/v1/fee-reductions")
async def create_fee_reduction(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    bill_no = body.get("bill_no")
    reduction_type = body.get("reduction_type")
    apply_amount = body.get("apply_amount")
    reason = body.get("reason")

    # Look up bill
    bill_id = None
    customer_id = 1
    currency_code = "CNY"
    contract_id = None
    if bill_no:
        bill = fetch_one(
            "SELECT id, customer_id, currency_code, contract_id FROM repayment_bill WHERE bill_no = %s",
            (bill_no,),
        )
        if bill:
            bill_id = bill["id"]
            customer_id = bill["customer_id"]
            currency_code = bill["currency_code"]
            contract_id = bill["contract_id"]

    reduction_no = gen_no("FR")
    now = datetime.datetime.now()

    row_id = insert(
        "INSERT INTO fee_reduction "
        "(reduction_no, bill_id, contract_id, customer_id, reduction_type, currency_code, "
        "apply_amount, approved_amount, approved_interest_amount, approved_fee_amount, "
        "approved_penalty_amount, reduction_status, approval_comment, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, %s, %s, %s)",
        (reduction_no, bill_id, contract_id, customer_id, reduction_type, currency_code,
         apply_amount, "pending", reason, now, now),
    )

    reduction = fetch_one("SELECT * FROM fee_reduction WHERE id = %s", (row_id,))
    result = _ser(reduction)
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 9. POST /api/v1/fee-reductions/{reduction_no}/approval
# ---------------------------------------------------------------------------

@router.post("/api/v1/fee-reductions/{reduction_no}/approval")
async def approve_fee_reduction(reduction_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    approval_result = body.get("approval_result")
    approved_amount = body.get("approved_amount")
    reason = body.get("reason")

    execute(
        "UPDATE fee_reduction SET reduction_status = %s, "
        "approved_amount = %s WHERE reduction_no = %s",
        ("approved", approved_amount, reduction_no),
    )

    result = {"reduction_status": "approved"}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp
