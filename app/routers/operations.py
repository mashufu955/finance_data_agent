"""Operations endpoints."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(prefix="/api/v1", tags=["operations"])


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


# ---------------------------------------------------------------------------
# POST /api/v1/notifications
# ---------------------------------------------------------------------------
@router.post("/notifications")
async def create_notification(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    customer_no = body.get("customer_no")
    message_type = body.get("message_type")
    send_channel = body.get("send_channel")
    related_type = body.get("related_type")
    message_title = body.get("message_title")
    message_content = body.get("message_content")

    customer = fetch_one("SELECT id FROM customer WHERE customer_no = %s", (customer_no,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    message_no = gen_no("NT")
    now = datetime.now()
    insert(
        """
        INSERT INTO notification_message
            (message_no, customer_id, related_type, message_type, send_channel,
             message_title, message_content, send_status, sent_at,
             read_status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'success', %s, 'unread', %s, %s)
        """,
        (
            message_no, customer_id, related_type, message_type, send_channel,
            message_title, message_content, now, now, now,
        ),
    )

    response_data = {"message_no": message_no, "send_status": "success"}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/support/tickets
# ---------------------------------------------------------------------------
@router.post("/support/tickets")
async def create_ticket(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    customer_no = body.get("customer_no")
    ticket_type = body.get("ticket_type")
    ticket_title = body.get("ticket_title")
    ticket_content = body.get("ticket_content")
    related_type = body.get("related_type")

    customer = fetch_one("SELECT id FROM customer WHERE customer_no = %s", (customer_no,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    channel = fetch_one(
        "SELECT id FROM dim_channel WHERE channel_code = %s",
        (channel_code,),
    )
    channel_id = channel["id"] if channel else 1

    ticket_no = gen_no("ST")
    now = datetime.now()
    insert(
        """
        INSERT INTO support_ticket
            (ticket_no, customer_id, channel_id, ticket_type, related_type,
             ticket_title, ticket_content, ticket_status, handle_result,
             submitted_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', '', %s, %s, %s)
        """,
        (
            ticket_no, customer_id, channel_id, ticket_type, related_type,
            ticket_title, ticket_content, now, now, now,
        ),
    )

    response_data = {
        "ticket_no": ticket_no,
        "ticket_status": "open",
        "ticket_type": ticket_type,
    }
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/support/tickets/{ticket_no}
# ---------------------------------------------------------------------------
@router.get("/support/tickets/{ticket_no}")
async def get_ticket(ticket_no: str):
    ticket = fetch_one("SELECT * FROM support_ticket WHERE ticket_no = %s", (ticket_no,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ok(_serialize(ticket))


# ---------------------------------------------------------------------------
# POST /api/v1/support/tickets/{ticket_no}/feedback
# ---------------------------------------------------------------------------
@router.post("/support/tickets/{ticket_no}/feedback")
async def submit_feedback(ticket_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    confirm_status = body.get("confirm_status")
    satisfaction_score = body.get("satisfaction_score")
    feedback_content = body.get("feedback_content")

    ticket = fetch_one("SELECT id, customer_id FROM support_ticket WHERE ticket_no = %s", (ticket_no,))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    feedback_no = gen_no("FB")
    now = datetime.now()
    insert(
        """
        INSERT INTO support_ticket_feedback
            (feedback_no, ticket_id, customer_id, confirm_status,
             satisfaction_score, feedback_content, confirmed_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            feedback_no, ticket["id"], ticket["customer_id"],
            confirm_status, satisfaction_score, feedback_content,
            now, now, now,
        ),
    )

    execute(
        "UPDATE support_ticket SET ticket_status = 'closed', closed_at = %s, updated_at = %s WHERE id = %s",
        (now, now, ticket["id"]),
    )

    response_data = {"feedback_no": feedback_no, "confirm_status": confirm_status}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/workflow/instances
# ---------------------------------------------------------------------------
@router.post("/workflow/instances")
async def create_workflow(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    workflow_type = body.get("workflow_type")
    related_type = body.get("related_type")
    related_id = body.get("related_id")
    initiator_type = body.get("initiator_type")
    initiator_no = body.get("initiator_no")

    instance_no = gen_no("WI")
    now = datetime.now()
    instance_id = insert(
        """
        INSERT INTO workflow_instance
            (instance_no, workflow_type, related_type, related_id,
             initiator_type, initiator_no, instance_status,
             started_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
        """,
        (
            instance_no, workflow_type, related_type, related_id,
            initiator_type, initiator_no, now, now, now,
        ),
    )

    task_no = gen_no("WT")
    insert(
        """
        INSERT INTO workflow_task
            (task_no, instance_id, node_code, node_name,
             task_status, assigned_at, created_at, updated_at)
        VALUES (%s, %s, 'process', 'Processing', 'pending', %s, %s, %s)
        """,
        (task_no, instance_id, now, now, now),
    )

    response_data = {
        "instance_no": instance_no,
        "instance_status": "pending",
        "tasks": [{"task_no": task_no, "task_status": "pending"}],
    }
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/workflow/instances/{instance_no}
# ---------------------------------------------------------------------------
@router.get("/workflow/instances/{instance_no}")
async def get_workflow_instance(instance_no: str):
    instance = fetch_one(
        "SELECT * FROM workflow_instance WHERE instance_no = %s",
        (instance_no,),
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")

    tasks = fetch_all(
        "SELECT * FROM workflow_task WHERE instance_id = %s",
        (instance["id"],),
    )

    result = {**_serialize(instance), "tasks": _serialize(tasks)}
    return ok(result)


# ---------------------------------------------------------------------------
# POST /api/v1/workflow/tasks/{task_no}/complete
# ---------------------------------------------------------------------------
@router.post("/workflow/tasks/{task_no}/complete")
async def complete_workflow_task(task_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idem(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    task_result = body.get("task_result")
    task_comment = body.get("task_comment")

    now = datetime.now()
    execute(
        "UPDATE workflow_task SET task_status = %s, task_result = %s, "
        "task_comment = %s, completed_at = %s, updated_at = %s WHERE task_no = %s",
        (task_result, task_result, task_comment, now, now, task_no),
    )

    task = fetch_one("SELECT instance_id FROM workflow_task WHERE task_no = %s", (task_no,))
    if task:
        execute(
            "UPDATE workflow_instance SET instance_status = %s, completed_at = %s, updated_at = %s WHERE id = %s",
            (task_result, now, now, task["instance_id"]),
        )

    response_data = {"instance_status": task_result}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/daily
# ---------------------------------------------------------------------------
@router.get("/metrics/daily")
async def list_daily_metrics(page_size: int = Query(10)):
    rows = fetch_all(
        "SELECT * FROM business_metric_dict WHERE yn = 1 ORDER BY id DESC LIMIT %s",
        (page_size,),
    )
    return list_ok(_serialize(rows), total_count=len(rows))
