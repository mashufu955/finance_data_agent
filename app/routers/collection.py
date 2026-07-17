"""Collection endpoints."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(prefix="/api/v1", tags=["collection"])


def _serialize(data: Any) -> Any:
    if isinstance(data, list):
        for row in data:
            _serialize(row)
        return data
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (datetime,)):
                data[key] = str(value)
        return data
    return data


def gen_no(prefix: str) -> str:
    return f"{prefix}{int(time.time() * 1000000)}"


def _idem(request: Request, body: dict) -> tuple[str, str, str, dict]:
    request_no = body.get("request_no", "")
    channel_code = request.headers.get("X-Channel-Code", "")
    operator_no = request.headers.get("X-Operator-No", "")
    return request_no, channel_code, operator_no, body


def _resolve_employee_id(employee_no: str) -> int | None:
    if not employee_no:
        return None
    row = fetch_one("SELECT id FROM dim_employee WHERE employee_no = %s", (employee_no,))
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases
# ---------------------------------------------------------------------------
@router.post("/collection/cases")
async def create_collection_case(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    overdue_no = body.get("overdue_no")
    collector_no = body.get("collector_no")
    collection_stage = body.get("collection_stage")

    overdue = fetch_one(
        "SELECT id, customer_id, contract_id, overdue_total_amount, currency_code "
        "FROM overdue_record WHERE overdue_no = %s",
        (overdue_no,),
    )
    if not overdue:
        raise HTTPException(status_code=404, detail="Overdue record not found")

    collector_id = _resolve_employee_id(collector_no)
    if collector_id is None:
        raise HTTPException(status_code=404, detail="Collector not found")

    case_no = gen_no("CC")
    now = datetime.now()
    insert(
        """
        INSERT INTO collection_case
            (case_no, overdue_id, contract_id, customer_id, collector_id,
             collection_stage, case_status, case_amount, assigned_at,
             created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s)
        """,
        (
            case_no, overdue["id"], overdue.get("contract_id"),
            overdue["customer_id"], collector_id, collection_stage,
            overdue["overdue_total_amount"], now, now, now,
        ),
    )

    response_data = {"case_no": case_no, "case_status": "open"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/collection/cases/{case_no}
# ---------------------------------------------------------------------------
@router.get("/collection/cases/{case_no}")
async def get_collection_case(case_no: str):
    case = fetch_one("SELECT * FROM collection_case WHERE case_no = %s", (case_no,))
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")
    return ok(_serialize(case))


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/actions
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/actions")
async def record_collection_action(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id, contract_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    action_no = gen_no("CA")
    emp_id = _resolve_employee_id(operator_no)
    now = datetime.now()
    insert(
        """
        INSERT INTO collection_action
            (action_no, case_id, customer_id, contract_id, action_type,
             action_status, action_result, operator_id, action_at,
             created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'completed', %s, %s, %s, %s, %s)
        """,
        (
            action_no, case["id"], case["customer_id"], case.get("contract_id"),
            body.get("action_type"), body.get("action_result"),
            emp_id, now, now, now,
        ),
    )

    response_data = {"action_no": action_no, "action_status": "completed"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/contacts
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/contacts")
async def record_collection_contact(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, collector_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    emp_id = _resolve_employee_id(operator_no)
    assistant_id = emp_id or case["collector_id"]
    now = datetime.now()

    insert(
        """
        INSERT INTO collection_contact_record
            (case_id, collector_id, assistant_collector_id, contact_method,
             contact_result, contact_content, contacted_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            case["id"], case["collector_id"], assistant_id,
            body.get("contact_method"), body.get("contact_result"),
            body.get("contact_content"), now, now,
        ),
    )

    response_data = {"contact_result": body.get("contact_result")}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/promises
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/promises")
async def create_promise_to_pay(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    promise_no = gen_no("CP")
    now = datetime.now()
    insert(
        """
        INSERT INTO repayment_promise
            (promise_no, case_id, customer_id, currency_code, promise_amount,
             promise_date, promise_status, fulfilled_amount, created_at, updated_at)
        VALUES (%s, %s, %s, 'CNY', %s, %s, 'active', 0, %s, %s)
        """,
        (
            promise_no, case["id"], case["customer_id"],
            body.get("promise_amount"), body.get("promise_date"),
            now, now,
        ),
    )

    response_data = {"promise_no": promise_no, "promise_status": "active"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/repayments
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/repayments")
async def collection_repayment(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id, contract_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    bill_no = body.get("bill_no")
    account_no = body.get("account_no")
    repayment_amount = body.get("repayment_amount")

    bill = fetch_one("SELECT id, contract_id, customer_id FROM repayment_bill WHERE bill_no = %s", (bill_no,))
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    account = fetch_one("SELECT id FROM bank_account WHERE account_no = %s", (account_no,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    repayment_no = gen_no("CR")
    now = datetime.now()
    insert(
        """
        INSERT INTO repayment_record
            (repayment_no, bill_id, contract_id, customer_id, account_id,
             repayment_type, currency_code, repayment_amount,
             principal_paid_amount, interest_paid_amount, fee_paid_amount,
             penalty_paid_amount, repayment_status, repaid_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'normal', 'CNY', %s, %s, 0, 0, 0, 'success', %s, %s, %s)
        """,
        (
            repayment_no, bill["id"], bill.get("contract_id"),
            bill["customer_id"], account["id"],
            repayment_amount, repayment_amount, now, now, now,
        ),
    )

    execute(
        "UPDATE repayment_bill SET paid_amount = paid_amount + %s, "
        "outstanding_amount = outstanding_amount - %s WHERE id = %s",
        (repayment_amount, repayment_amount, bill["id"]),
    )

    response_data = {"repayment_no": repayment_no, "repayment_status": "success"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/legal-cases
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/legal-cases")
async def create_legal_case(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id, contract_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    legal_case_no = gen_no("LC")
    now = datetime.now()
    insert(
        """
        INSERT INTO legal_case
            (legal_case_no, case_id, contract_id, customer_id, legal_type,
             legal_status, claim_amount, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'submitted', %s, %s, %s)
        """,
        (
            legal_case_no, case["id"], case.get("contract_id"),
            case["customer_id"], body.get("legal_type"),
            body.get("claim_amount"), now, now,
        ),
    )

    response_data = {"legal_case_no": legal_case_no, "legal_status": "submitted"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/write-offs
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/write-offs")
async def create_write_off(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id, contract_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    write_off_no = gen_no("WO")
    now = datetime.now()
    insert(
        """
        INSERT INTO loan_write_off
            (write_off_no, case_id, contract_id, customer_id, currency_code,
             apply_amount, approved_amount, approved_principal_amount,
             approved_interest_amount, approved_fee_amount, approved_penalty_amount,
             write_off_status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 'CNY', %s, 0, 0, 0, 0, 0, 'pending', %s, %s)
        """,
        (
            write_off_no, case["id"], case.get("contract_id"),
            case["customer_id"], body.get("apply_amount"), now, now,
        ),
    )

    response_data = {"write_off_no": write_off_no, "write_off_status": "pending"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/write-offs/{write_off_no}/approval
# ---------------------------------------------------------------------------
@router.post("/collection/write-offs/{write_off_no}/approval")
async def approve_write_off(write_off_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    wo = fetch_one(
        "SELECT id FROM loan_write_off WHERE write_off_no = %s",
        (write_off_no,),
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Write-off not found")

    emp_id = _resolve_employee_id(operator_no)
    now = datetime.now()
    execute(
        "UPDATE loan_write_off SET write_off_status = 'approved', "
        "approved_by = %s, approved_amount = apply_amount, "
        "approved_principal_amount = apply_amount, "
        "approved_at = %s WHERE id = %s",
        (emp_id, now, wo["id"]),
    )

    response_data = {"write_off_status": "approved"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/write-offs/{write_off_no}/post
# ---------------------------------------------------------------------------
@router.post("/collection/write-offs/{write_off_no}/post")
async def post_write_off(write_off_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    wo = fetch_one(
        "SELECT id FROM loan_write_off WHERE write_off_no = %s",
        (write_off_no,),
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Write-off not found")

    now = datetime.now()
    execute(
        "UPDATE loan_write_off SET write_off_status = 'posted', posted_at = %s WHERE id = %s",
        (now, wo["id"]),
    )

    response_data = {"write_off_status": "posted"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/restructures
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/restructures")
async def create_restructure(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id, contract_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    restructure_no = gen_no("RS")
    now = datetime.now()
    insert(
        """
        INSERT INTO loan_restructure
            (restructure_no, case_id, contract_id, customer_id,
             before_outstanding_principal_amount, capitalized_amount,
             reduced_amount, after_outstanding_principal_amount,
             original_schedule_version, new_schedule_version,
             restructure_type, new_term_months, new_interest_rate,
             restructure_status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 0, 0, %s, 0, 0, %s, %s, %s, 'pending', %s, %s)
        """,
        (
            restructure_no, case["id"], case.get("contract_id"),
            case["customer_id"],
            body.get("restructure_principal_amount"),
            body.get("restructure_principal_amount"),
            body.get("restructure_type"),
            body.get("new_term_months"),
            body.get("new_interest_rate"),
            now, now,
        ),
    )

    response_data = {"restructure_no": restructure_no, "restructure_status": "pending"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/restructures/{restructure_no}/approval
# ---------------------------------------------------------------------------
@router.post("/collection/restructures/{restructure_no}/approval")
async def approve_restructure(restructure_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    rs = fetch_one(
        "SELECT id FROM loan_restructure WHERE restructure_no = %s",
        (restructure_no,),
    )
    if not rs:
        raise HTTPException(status_code=404, detail="Restructure not found")

    emp_id = _resolve_employee_id(operator_no)
    now = datetime.now()
    execute(
        "UPDATE loan_restructure SET restructure_status = 'approved', "
        "approved_by = %s, approved_at = %s WHERE id = %s",
        (emp_id, now, rs["id"]),
    )

    response_data = {"restructure_status": "approved"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/restructures/{restructure_no}/effective
# ---------------------------------------------------------------------------
@router.post("/collection/restructures/{restructure_no}/effective")
async def effective_restructure(restructure_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    rs = fetch_one(
        "SELECT id FROM loan_restructure WHERE restructure_no = %s",
        (restructure_no,),
    )
    if not rs:
        raise HTTPException(status_code=404, detail="Restructure not found")

    now = datetime.now()
    execute(
        "UPDATE loan_restructure SET restructure_status = 'effective', effective_at = %s WHERE id = %s",
        (now, rs["id"]),
    )

    response_data = {"restructure_status": "effective"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/collection/cases/{case_no}/collateral-disposals
# ---------------------------------------------------------------------------
@router.post("/collection/cases/{case_no}/collateral-disposals")
async def dispose_collateral(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    case = fetch_one(
        "SELECT id, customer_id, contract_id FROM collection_case WHERE case_no = %s",
        (case_no,),
    )
    if not case:
        raise HTTPException(status_code=404, detail="Collection case not found")

    collateral_no_str = body.get("collateral_no")
    collateral = fetch_one(
        "SELECT id FROM collateral_asset WHERE collateral_no = %s",
        (collateral_no_str,),
    )
    if not collateral:
        raise HTTPException(status_code=404, detail="Collateral not found")

    account_no = body.get("account_no")
    account = fetch_one("SELECT id FROM bank_account WHERE account_no = %s", (account_no,))
    account_id = account["id"] if account else None

    disposal_no = gen_no("CD")
    now = datetime.now()
    insert(
        """
        INSERT INTO collateral_disposal
            (disposal_no, case_id, collateral_id, contract_id, customer_id,
             currency_code, disposal_method, disposal_amount, received_amount,
             disposal_status, completed_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'CNY', %s, %s, %s, 'completed', %s, %s, %s)
        """,
        (
            disposal_no, case["id"], collateral["id"], case.get("contract_id"),
            case["customer_id"], body.get("disposal_method"),
            body.get("disposal_amount"), body.get("received_amount"),
            now, now, now,
        ),
    )

    execute(
        "UPDATE collateral_asset SET collateral_status = 'disposed' WHERE id = %s",
        (collateral["id"],),
    )

    response_data = {"disposal_no": disposal_no, "collateral_status": "disposed"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/collection/performance-daily
# ---------------------------------------------------------------------------
@router.get("/collection/performance-daily")
async def list_performance_daily(page_size: int = Query(10)):
    rows = fetch_all(
        "SELECT * FROM collection_performance_daily ORDER BY stat_date DESC LIMIT %s",
        (page_size,),
    )
    return list_ok(_serialize(rows), total_count=len(rows))
