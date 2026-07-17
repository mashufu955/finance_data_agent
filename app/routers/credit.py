"""Credit application and loan product endpoints."""

from __future__ import annotations

import datetime
import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(tags=["credit"])

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


# ---------------------------------------------------------------------------
# 1. GET /api/v1/loan/products
# ---------------------------------------------------------------------------

@router.get("/api/v1/loan/products")
def list_loan_products(currency_code: str = Query(None)):
    if currency_code:
        rows = fetch_all(
            "SELECT * FROM loan_product WHERE product_status IN ('selling','active') AND currency_code = %s",
            (currency_code,),
        )
    else:
        rows = fetch_all(
            "SELECT * FROM loan_product WHERE product_status IN ('selling','active')"
        )
    return list_ok(_ser(rows), total_count=len(rows))


# ---------------------------------------------------------------------------
# 2. GET /api/v1/loan/products/{product_code}
# ---------------------------------------------------------------------------

@router.get("/api/v1/loan/products/{product_code}")
def get_loan_product(product_code: str):
    row = fetch_one(
        "SELECT * FROM loan_product WHERE product_code = %s", (product_code,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Loan product not found")
    return ok(_ser(row))


# ---------------------------------------------------------------------------
# 3. POST /api/v1/credit/applications
# ---------------------------------------------------------------------------

@router.post("/api/v1/credit/applications")
async def create_credit_application(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    customer_no = body["customer_no"]
    product_code = body["product_code"]
    apply_limit_amount = body.get("apply_limit_amount")
    materials = body.get("materials", [])

    # -- look-ups --
    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s", (customer_no,)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    product = fetch_one(
        "SELECT id FROM loan_product WHERE product_code = %s", (product_code,)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Loan product not found")
    product_id = product["id"]

    channel = fetch_one(
        "SELECT id FROM dim_channel WHERE channel_code = %s", (ch,)
    )
    channel_id = channel["id"] if channel else None

    credit_application_no = gen_no("CA")
    currency_code = body.get("currency_code", "CNY")
    now = datetime.datetime.now()

    # -- insert credit_application --
    app_id = insert(
        "INSERT INTO credit_application "
        "(credit_application_no, customer_id, product_id, channel_id, "
        "apply_limit_amount, currency_code, application_status, submitted_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (credit_application_no, customer_id, product_id, channel_id, apply_limit_amount, currency_code, "submitted", now, now, now),
    )

    # -- insert materials --
    for mat in materials:
        material_no = gen_no("CAM")
        insert(
            "INSERT INTO credit_application_material "
            "(material_no, credit_application_id, customer_id, material_type, material_name, "
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

    result = {
        "credit_application_no": credit_application_no,
        "application_status": "submitted",
    }
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 4. GET /api/v1/credit/applications/{credit_application_no}
# ---------------------------------------------------------------------------

@router.get("/api/v1/credit/applications/{credit_application_no}")
def get_credit_application(credit_application_no: str):
    row = fetch_one(
        "SELECT * FROM credit_application WHERE credit_application_no = %s",
        (credit_application_no,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Credit application not found")
    return ok(_ser(row))


# ---------------------------------------------------------------------------
# 5. POST /api/v1/credit/applications/{credit_application_no}/approval-records
# ---------------------------------------------------------------------------

@router.post("/api/v1/credit/applications/{credit_application_no}/approval-records")
async def approve_credit_application(credit_application_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    approval_node = body.get("approval_node")
    approval_result = body.get("approval_result")
    approved_limit_amount = body.get("approved_limit_amount")
    approval_comment = body.get("approval_comment")

    # -- look up credit application --
    app = fetch_one(
        "SELECT id, customer_id, product_id, currency_code FROM credit_application WHERE credit_application_no = %s",
        (credit_application_no,),
    )
    if not app:
        raise HTTPException(status_code=404, detail="Credit application not found")
    app_id = app["id"]
    customer_id = app["customer_id"]
    product_id = app["product_id"]
    currency_code = app["currency_code"]

    # -- look up approver from dim_employee --
    employee = fetch_one(
        "SELECT id FROM dim_employee WHERE employee_no = %s", (op,)
    )
    approver_id = employee["id"] if employee else None

    # -- insert credit_approval_record --
    now = datetime.datetime.now()
    insert(
        "INSERT INTO credit_approval_record "
        "(credit_application_id, approval_node, approval_round, approver_id, approval_result, "
        "approved_limit_amount, approval_comment, approved_at, created_at) "
        "VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s)",
        (app_id, approval_node, approver_id, approval_result, approved_limit_amount, approval_comment, now, now),
    )

    # -- update credit_application --
    execute(
        "UPDATE credit_application SET application_status = %s, approved_at = NOW() "
        "WHERE id = %s",
        ("approved", app_id),
    )

    # -- create credit_limit --
    limit_no = gen_no("CL")
    valid_from = now.date()
    valid_to = valid_from + datetime.timedelta(days=365)
    insert(
        "INSERT INTO credit_limit "
        "(limit_no, credit_application_id, customer_id, product_id, currency_code, "
        "limit_status, total_limit_amount, used_limit_amount, frozen_limit_amount, "
        "available_limit_amount, valid_from, valid_to, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, %s)",
        (limit_no, app_id, customer_id, product_id, currency_code,
         "active", approved_limit_amount, approved_limit_amount, valid_from, valid_to, now, now),
    )

    result = {"application_status": "approved"}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp
