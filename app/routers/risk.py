"""Risk and AML endpoints."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(prefix="/api/v1", tags=["risk"])


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
# POST /api/v1/risk/events
# ---------------------------------------------------------------------------
@router.post("/risk/events")
async def create_risk_event(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    customer_no = body.get("customer_no")
    related_type = body.get("related_type")
    related_id = body.get("related_id")
    event_type = body.get("event_type")
    risk_score = body.get("risk_score", 0)

    customer = fetch_one("SELECT id FROM customer WHERE customer_no = %s", (customer_no,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    strategy = fetch_one(
        "SELECT id FROM risk_strategy WHERE applicable_event_type = %s AND strategy_status = 'active' LIMIT 1",
        (event_type,),
    )
    strategy_id = strategy["id"] if strategy else 1

    risk_level = fetch_one(
        "SELECT id FROM dim_risk_level WHERE yn = 1 AND risk_level_type = 'event' ORDER BY sort_no LIMIT 1"
    )
    risk_level_id = risk_level["id"] if risk_level else 1

    event_no = gen_no("RE")
    now = datetime.now()
    event_id = insert(
        """
        INSERT INTO risk_event
            (event_no, customer_id, event_type, related_type, related_id,
             strategy_id, risk_level_id, risk_score, decision_action,
             hit_flag, event_status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'review', 1, 'created', %s, %s)
        """,
        (
            event_no, customer_id, event_type, related_type, related_id,
            strategy_id, risk_level_id, risk_score, now, now,
        ),
    )

    manual_review_task = None
    if risk_score >= 80:
        instance_no = gen_no("WI")
        instance_id = insert(
            """
            INSERT INTO workflow_instance
                (instance_no, workflow_type, related_type, related_id,
                 initiator_type, initiator_no, instance_status,
                 started_at, created_at, updated_at)
            VALUES (%s, 'manual_review', 'risk_event', %s, 'system', 'auto', 'pending', %s, %s, %s)
            """,
            (instance_no, event_id, now, now, now),
        )

        task_no = gen_no("WT")
        insert(
            """
            INSERT INTO workflow_task
                (task_no, instance_id, node_code, node_name,
                 task_status, assigned_at, created_at, updated_at)
            VALUES (%s, %s, 'review', 'Manual Review', 'pending', %s, %s, %s)
            """,
            (task_no, instance_id, now, now, now),
        )

        manual_review_task = {"task_no": task_no, "task_status": "pending"}

    response_data = {
        "event_no": event_no,
        "event_status": "created",
        "hit_flag": 1,
        "decision_action": "review",
        "manual_review_task": manual_review_task,
    }
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/risk/events/{event_no}
# ---------------------------------------------------------------------------
@router.get("/risk/events/{event_no}")
async def get_risk_event(event_no: str):
    event = fetch_one("SELECT * FROM risk_event WHERE event_no = %s", (event_no,))
    if not event:
        raise HTTPException(status_code=404, detail="Risk event not found")

    manual_review_task = fetch_one(
        "SELECT wt.task_no, wt.task_status FROM workflow_task wt "
        "JOIN workflow_instance wi ON wt.instance_id = wi.id "
        "WHERE wi.related_type = 'risk_event' AND wi.related_id = %s "
        "AND wi.workflow_type = 'manual_review' LIMIT 1",
        (event["id"],),
    )

    result = {**_serialize(event), "manual_review_task": _serialize(manual_review_task) if manual_review_task else None}
    return ok(result)


# ---------------------------------------------------------------------------
# POST /api/v1/manual-review/tasks/{task_no}/complete
# ---------------------------------------------------------------------------
@router.post("/manual-review/tasks/{task_no}/complete")
async def complete_manual_review(task_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    review_result = body.get("review_result")
    review_comment = body.get("review_comment")

    now = datetime.now()
    execute(
        "UPDATE workflow_task SET task_status = %s, task_result = %s, "
        "task_comment = %s, completed_at = %s, updated_at = %s WHERE task_no = %s",
        (review_result, review_result, review_comment, now, now, task_no),
    )

    task = fetch_one("SELECT instance_id FROM workflow_task WHERE task_no = %s", (task_no,))
    if task:
        execute(
            "UPDATE workflow_instance SET instance_status = %s, completed_at = %s, updated_at = %s WHERE id = %s",
            (review_result, now, now, task["instance_id"]),
        )

    response_data = {"task_status": review_result}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/blacklists
# ---------------------------------------------------------------------------
@router.post("/blacklists")
async def create_blacklist(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    subject_type = body.get("subject_type")
    subject_value = body.get("subject_value")
    risk_level_code = body.get("risk_level_code")
    reason = body.get("reason")
    effective_from = body.get("effective_from")
    effective_to = body.get("effective_to")

    risk_level = fetch_one(
        "SELECT id FROM dim_risk_level WHERE risk_level_code = %s",
        (risk_level_code,),
    )
    risk_level_id = risk_level["id"] if risk_level else 1

    blacklist_no = gen_no("BL")
    now = datetime.now()
    insert(
        """
        INSERT INTO blacklist_record
            (blacklist_no, subject_type, subject_value, risk_level_id,
             blacklist_reason, blacklist_status, effective_from, effective_to,
             created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s)
        """,
        (
            blacklist_no, subject_type, subject_value, risk_level_id,
            reason, effective_from, effective_to, now, now,
        ),
    )

    response_data = {
        "blacklist_no": blacklist_no,
        "blacklist_status": "active",
    }
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/blacklists
# ---------------------------------------------------------------------------
@router.get("/blacklists")
async def list_blacklists(customer_no: str = Query(None)):
    if customer_no:
        rows = fetch_all(
            "SELECT * FROM blacklist_record WHERE subject_value = %s",
            (customer_no,),
        )
    else:
        rows = fetch_all("SELECT * FROM blacklist_record")
    return list_ok(_serialize(rows), total_count=len(rows))


# ---------------------------------------------------------------------------
# POST /api/v1/aml/cases
# ---------------------------------------------------------------------------
@router.post("/aml/cases")
async def create_aml_case(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    customer_no = body.get("customer_no")
    risk_event_no = body.get("risk_event_no")
    case_type = body.get("case_type")
    suspicious_reason = body.get("suspicious_reason")
    transactions = body.get("transactions", [])

    customer = fetch_one("SELECT id FROM customer WHERE customer_no = %s", (customer_no,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    risk_event = fetch_one("SELECT id FROM risk_event WHERE event_no = %s", (risk_event_no,))
    risk_event_id = risk_event["id"] if risk_event else None

    risk_level = fetch_one(
        "SELECT id FROM dim_risk_level WHERE yn = 1 AND risk_level_type = 'event' ORDER BY sort_no LIMIT 1"
    )
    risk_level_id = risk_level["id"] if risk_level else 1

    first_txn = None
    total_amount = 0
    txn_ids = []
    for txn in transactions:
        txn_row = fetch_one(
            "SELECT id, transaction_amount FROM account_transaction WHERE transaction_no = %s",
            (txn.get("transaction_no"),),
        )
        if txn_row:
            txn_ids.append((txn_row["id"], txn_row["transaction_amount"], txn))
            if first_txn is None:
                first_txn = txn_row["id"]
            total_amount += float(txn_row["transaction_amount"])

    case_no = gen_no("AML")
    now = datetime.now()
    case_id = insert(
        """
        INSERT INTO aml_case
            (case_no, risk_event_id, customer_id, primary_transaction_id,
             transaction_count, total_transaction_amount, currency_code,
             case_type, case_status, risk_level_id, case_summary,
             opened_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'CNY', %s, 'investigating', %s, %s, %s, %s, %s)
        """,
        (
            case_no, risk_event_id, customer_id, first_txn,
            len(transactions), total_amount,
            case_type, risk_level_id, suspicious_reason,
            now, now, now,
        ),
    )

    for txn_id, txn_amount, txn in txn_ids:
        insert(
            """
            INSERT INTO aml_case_transaction
                (aml_case_id, transaction_id, customer_id, currency_code,
                 transaction_amount, included_flag, include_reason, created_at)
            VALUES (%s, %s, %s, 'CNY', %s, %s, %s, %s)
            """,
            (
                case_id, txn_id, customer_id, txn_amount,
                txn.get("included_flag", 1), txn.get("include_reason", ""),
                now,
            ),
        )

    response_data = {
        "case_no": case_no,
        "case_status": "investigating",
    }
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/aml/cases/{case_no}/review-results
# ---------------------------------------------------------------------------
@router.post("/aml/cases/{case_no}/review-results")
async def submit_aml_review(case_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    review_result = body.get("review_result")
    report_flag = body.get("report_flag")
    review_comment = body.get("review_comment")

    case = fetch_one("SELECT * FROM aml_case WHERE case_no = %s", (case_no,))
    if not case:
        raise HTTPException(status_code=404, detail="AML case not found")

    emp_id = _resolve_employee_id(operator_no) or 1
    now = datetime.now()

    review_no = gen_no("ARR")
    insert(
        """
        INSERT INTO aml_review_result
            (review_no, aml_case_id, risk_event_id, reviewer_id,
             review_result, review_comment, reviewed_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            review_no, case["id"], case["risk_event_id"], emp_id,
            review_result, review_comment, now, now,
        ),
    )

    response_data = {}

    if report_flag:
        report_no = gen_no("STR")
        insert(
            """
            INSERT INTO suspicious_transaction_report
                (report_no, aml_case_id, customer_id, transaction_count,
                 total_transaction_amount, currency_code,
                 report_period_start, report_period_end, report_type,
                 report_status, reported_at, report_content,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'CNY', %s, %s, 'suspicious', 'submitted', %s, %s, %s, %s)
            """,
            (
                report_no, case["id"], case["customer_id"],
                case["transaction_count"], case["total_transaction_amount"],
                case["opened_at"].date() if hasattr(case["opened_at"], 'date') else now.date(),
                now.date(), now, review_comment or "Suspicious transaction report",
                now, now,
            ),
        )

        execute(
            "UPDATE aml_case SET case_status = 'reported' WHERE id = %s",
            (case["id"],),
        )

        response_data = {"report_no": report_no}

    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/aml/reports/{report_no}
# ---------------------------------------------------------------------------
@router.get("/aml/reports/{report_no}")
async def get_aml_report(report_no: str):
    report = fetch_one(
        "SELECT * FROM suspicious_transaction_report WHERE report_no = %s",
        (report_no,),
    )
    if not report:
        raise HTTPException(status_code=404, detail="AML report not found")
    return ok(_serialize(report))
