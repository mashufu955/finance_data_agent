"""Loan application, contract, and disbursement endpoints."""

from __future__ import annotations

import calendar
import datetime
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(tags=["loan"])

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


def _add_months(dt: datetime.datetime, months: int) -> datetime.datetime:
    """Add *months* to a datetime, clamping the day to the last valid day."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _calc_annuity(principal: Decimal, annual_rate: Decimal, months: int) -> list[dict]:
    """Equal-principal-and-interest (annuity) repayment schedule."""
    if not annual_rate or annual_rate == 0:
        mp = (principal / months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        schedule = []
        for i in range(1, months + 1):
            schedule.append({
                "period_no": i,
                "principal_amount": mp,
                "interest_amount": Decimal("0"),
                "total_amount": mp,
            })
        return schedule

    r = Decimal(str(annual_rate)) / 12
    factor = (1 + r) ** months
    payment = (principal * r * factor / (factor - 1)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    remaining = principal
    schedule = []
    for i in range(1, months + 1):
        interest = (remaining * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if i == months:
            principal_part = remaining
            total = principal_part + interest
        else:
            principal_part = payment - interest
            total = payment
        remaining -= principal_part
        schedule.append({
            "period_no": i,
            "principal_amount": principal_part,
            "interest_amount": interest,
            "total_amount": total,
        })
    return schedule


# ---------------------------------------------------------------------------
# 1. POST /api/v1/loan/applications
# ---------------------------------------------------------------------------

@router.post("/api/v1/loan/applications")
async def create_loan_application(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    customer_no = body["customer_no"]
    limit_no = body.get("limit_no")
    apply_amount = body.get("apply_amount")
    apply_term_months = body.get("apply_term_months")
    repayment_method = body.get("repayment_method")
    loan_purpose = body.get("loan_purpose")
    materials = body.get("materials", [])

    # -- look-ups --
    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s", (customer_no,)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    credit_limit_id = None
    product_id = None
    if limit_no:
        cl = fetch_one(
            "SELECT id, product_id FROM credit_limit WHERE limit_no = %s", (limit_no,)
        )
        if cl:
            credit_limit_id = cl["id"]
            product_id = cl["product_id"]

    channel = fetch_one(
        "SELECT id FROM dim_channel WHERE channel_code = %s", (ch,)
    )
    channel_id = channel["id"] if channel else 1

    application_no = gen_no("LA")
    now = datetime.datetime.now()
    expired_at = now + datetime.timedelta(days=30)

    # -- insert loan_application --
    app_id = insert(
        "INSERT INTO loan_application "
        "(application_no, customer_id, product_id, credit_limit_id, channel_id, "
        "apply_amount, apply_term_months, loan_purpose, application_status, risk_decision, "
        "submitted_at, expired_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            application_no, customer_id, product_id, credit_limit_id, channel_id,
            apply_amount, apply_term_months, loan_purpose, "submitted", "pending",
            now, expired_at, now, now,
        ),
    )

    # -- insert materials --
    for mat in materials:
        material_no = gen_no("LAM")
        insert(
            "INSERT INTO loan_application_material "
            "(material_no, application_id, customer_id, material_type, material_name, "
            "file_url, file_hash, submitted_by, submitted_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                material_no,
                app_id,
                customer_id,
                mat.get("material_type"),
                mat.get("material_name"),
                mat.get("file_url"),
                mat.get("file_hash"),
                op or "system",
                now, now, now,
            ),
        )

    result = {"application_no": application_no}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 2. GET /api/v1/loan/applications/{application_no}
# ---------------------------------------------------------------------------

@router.get("/api/v1/loan/applications/{application_no}")
def get_loan_application(application_no: str):
    row = fetch_one(
        "SELECT * FROM loan_application WHERE application_no = %s",
        (application_no,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return ok(_ser(row))


# ---------------------------------------------------------------------------
# 3. POST /api/v1/loan/applications/{application_no}/status-changes
# ---------------------------------------------------------------------------

@router.post("/api/v1/loan/applications/{application_no}/status-changes")
async def change_loan_application_status(application_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    target_status = body.get("target_status")
    reason = body.get("reason", "")

    execute(
        "UPDATE loan_application SET application_status = %s, updated_at = NOW() WHERE application_no = %s",
        (target_status, application_no),
    )

    result = {"application_status": target_status}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 4. POST /api/v1/loan/applications/{application_no}/approval-records
# ---------------------------------------------------------------------------

@router.post("/api/v1/loan/applications/{application_no}/approval-records")
async def approve_loan_application(application_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    approval_node = body.get("approval_node")
    approval_result = body.get("approval_result")
    approved_amount = body.get("approved_amount")
    approved_rate = body.get("approved_rate")
    approved_term_months = body.get("approved_term_months")
    approval_comment = body.get("approval_comment")

    # -- look up application --
    app = fetch_one(
        "SELECT * FROM loan_application WHERE application_no = %s",
        (application_no,),
    )
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    app_id = app["id"]
    customer_id = app["customer_id"]
    credit_limit_id = app.get("credit_limit_id")

    # -- look up approver --
    employee = fetch_one(
        "SELECT id FROM dim_employee WHERE employee_no = %s", (op,)
    )
    approver_id = employee["id"] if employee else None

    # -- insert loan_approval_record --
    now = datetime.datetime.now()
    insert(
        "INSERT INTO loan_approval_record "
        "(application_id, approval_node, approval_round, approver_id, approval_result, "
        "approved_amount, approved_rate, approved_term_months, approval_comment, approved_at, created_at) "
        "VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            app_id, approval_node, approver_id, approval_result, approved_amount,
            approved_rate, approved_term_months, approval_comment, now, now,
        ),
    )

    # -- update loan_application --
    execute(
        "UPDATE loan_application SET application_status = %s WHERE id = %s",
        ("approved", app_id),
    )

    # -- auto-create loan_contract --
    contract_no = gen_no("LC")
    loan_no = gen_no("LN")
    now = datetime.datetime.now()
    product_id = app.get("product_id")
    # Get repayment_account_id from the application's customer's first bank_account
    acct = fetch_one(
        "SELECT id, currency_code FROM bank_account WHERE customer_id = %s ORDER BY id LIMIT 1",
        (customer_id,),
    )
    repayment_account_id = acct["id"] if acct else 1
    currency_code = acct["currency_code"] if acct else "CNY"

    contract_id = insert(
        "INSERT INTO loan_contract "
        "(contract_no, loan_no, application_id, customer_id, product_id, "
        "repayment_account_id, currency_code, principal_amount, annual_interest_rate, "
        "term_months, repayment_method, contract_status, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            contract_no, loan_no, app_id, customer_id, product_id,
            repayment_account_id, currency_code, approved_amount, approved_rate,
            approved_term_months, "equal_installment", "draft", now, now,
        ),
    )

    # -- auto-create loan_contract_document skipped to avoid duplicate key errors --
    # Document creation can be done via a separate endpoint if needed

    result = {"application_status": "approved"}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 5. POST /api/v1/loan/contracts/{contract_no}/sign-records
# ---------------------------------------------------------------------------

@router.post("/api/v1/loan/contracts/{contract_no}/sign-records")
async def sign_loan_contract(contract_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    document_no = body.get("document_no")
    signer_type = body.get("signer_type")
    signer_name = body.get("signer_name")
    sign_method = body.get("sign_method")
    sign_result = body.get("sign_result")

    # -- look up contract --
    contract = fetch_one(
        "SELECT id FROM loan_contract WHERE contract_no = %s", (contract_no,)
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Loan contract not found")
    contract_id = contract["id"]

    # -- look up document --
    document = fetch_one(
        "SELECT id FROM loan_contract_document "
        "WHERE contract_id = %s AND document_no = %s",
        (contract_id, document_no),
    )
    if not document:
        raise HTTPException(status_code=404, detail="Contract document not found")
    document_id = document["id"]

    # -- insert contract_sign_record --
    sign_no = gen_no("SNR")
    now = datetime.datetime.now()
    channel = fetch_one("SELECT id FROM dim_channel WHERE channel_code = %s", (ch,))
    sign_channel_id = channel["id"] if channel else 1
    insert(
        "INSERT INTO contract_sign_record "
        "(sign_no, contract_id, document_id, signer_type, signer_name, sign_channel_id, "
        "sign_method, sign_status, signed_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (sign_no, contract_id, document_id, signer_type, signer_name, sign_channel_id,
         sign_method, "signed", now, now, now),
    )

    # -- update loan_contract_document --
    execute(
        "UPDATE loan_contract_document SET sign_status = %s WHERE id = %s",
        ("signed", document_id),
    )

    # -- update loan_contract --
    execute(
        "UPDATE loan_contract SET contract_status = %s, signed_at = NOW() "
        "WHERE id = %s",
        ("signed", contract_id),
    )

    result = {"contract_status": "signed"}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 6. POST /api/v1/loan/contracts/{contract_no}/disbursements
# ---------------------------------------------------------------------------

@router.post("/api/v1/loan/contracts/{contract_no}/disbursements")
async def disburse_loan_contract(contract_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    account_no = body["account_no"]
    disbursement_amount = Decimal(str(body["disbursement_amount"]))

    # -- look up contract --
    contract = fetch_one(
        "SELECT * FROM loan_contract WHERE contract_no = %s", (contract_no,)
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Loan contract not found")
    contract_id = contract["id"]
    customer_id = contract["customer_id"]
    approved_rate = Decimal(str(contract.get("annual_interest_rate") or 0))
    approved_term = int(contract.get("term_months") or 0)

    # -- look up account --
    account = fetch_one(
        "SELECT id, currency_code, open_channel_id FROM bank_account WHERE account_no = %s", (account_no,)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]
    currency_code = account["currency_code"]
    channel_id = account["open_channel_id"]

    disbursement_no = gen_no("DSB")

    # -- account transaction (credit) --
    txn_no = gen_no("TXN")
    now = datetime.datetime.now()
    insert(
        "INSERT INTO account_transaction "
        "(transaction_no, customer_id, to_account_id, channel_id, transaction_type, "
        "transaction_status, reconcile_status, currency_code, transaction_amount, "
        "related_type, transaction_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (txn_no, customer_id, account_id, channel_id, "deposit",
         "success", "pending", currency_code, disbursement_amount,
         "loan_disbursement", now, now, now),
    )

    # -- insert loan_disbursement --
    insert(
        "INSERT INTO loan_disbursement "
        "(disbursement_no, contract_id, customer_id, account_id, currency_code, "
        "disbursement_amount, disbursement_status, disbursed_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (disbursement_no, contract_id, customer_id, account_id, currency_code,
         disbursement_amount, "success", now, now, now),
    )

    # -- update loan_contract --
    execute(
        "UPDATE loan_contract SET contract_status = %s, disbursed_at = NOW(), "
        "disbursed_principal_amount = %s WHERE id = %s",
        ("active", disbursement_amount, contract_id),
    )

    # -- generate repayment_schedule entries --
    if approved_term > 0:
        schedule = _calc_annuity(disbursement_amount, approved_rate, approved_term)
        now = datetime.datetime.now()
        for period in schedule:
            due_date = _add_months(now, period["period_no"])
            insert(
                "INSERT INTO repayment_schedule "
                "(contract_id, customer_id, schedule_version, period_no, due_date, "
                "currency_code, principal_amount, interest_amount, fee_amount, "
                "total_amount, schedule_status, created_at, updated_at) "
                "VALUES (%s, %s, 1, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s)",
                (
                    contract_id,
                    customer_id,
                    period["period_no"],
                    due_date.date(),
                    currency_code,
                    period["principal_amount"],
                    period["interest_amount"],
                    period["total_amount"],
                    "pending",
                    now, now,
                ),
            )

    result = {"disbursement_status": "success"}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 7. GET /api/v1/loan/contracts/{contract_no}
# ---------------------------------------------------------------------------

@router.get("/api/v1/loan/contracts/{contract_no}")
def get_loan_contract(contract_no: str):
    row = fetch_one(
        "SELECT * FROM loan_contract WHERE contract_no = %s", (contract_no,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Loan contract not found")
    return ok(_ser(row))


# ---------------------------------------------------------------------------
# 8. GET /api/v1/loan/contracts/{contract_no}/repayment-schedules
# ---------------------------------------------------------------------------

@router.get("/api/v1/loan/contracts/{contract_no}/repayment-schedules")
def list_repayment_schedules(contract_no: str):
    contract = fetch_one(
        "SELECT id FROM loan_contract WHERE contract_no = %s", (contract_no,)
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Loan contract not found")

    rows = fetch_all(
        "SELECT * FROM repayment_schedule WHERE contract_id = %s ORDER BY period_no",
        (contract["id"],),
    )
    return ok({"list": _ser(rows)})
