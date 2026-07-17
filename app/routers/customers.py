"""Customer management endpoints."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(prefix="/api/v1", tags=["customers"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(data: Any) -> Any:
    """Convert datetime/date/Decimal values to plain strings for JSON safety."""
    if isinstance(data, list):
        for row in data:
            _serialize(row)
        return data
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (datetime, date)):
                data[key] = str(value)
            elif isinstance(value, (list, dict)):
                _serialize(value)
        return data
    return data


def _get_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


def _check_auth(request: Request, customer_no: str) -> None:
    token = _get_bearer_token(request)
    if token != customer_no:
        raise HTTPException(status_code=403, detail="Forbidden")


def _idempotency_params(request: Request, body: dict) -> tuple[str, str, str, dict]:
    request_no = body.get("request_no", "")
    channel_code = request.headers.get("X-Channel-Code", "")
    operator_no = request.headers.get("X-Operator-No", "")
    return request_no, channel_code, operator_no, body


def gen_no(prefix: str) -> str:
    return f"{prefix}{int(time.time() * 1000000)}"


def _resolve_employee_id(employee_no: str) -> int | None:
    """Resolve employee number to dim_employee.id."""
    if not employee_no:
        return None
    row = fetch_one("SELECT id FROM dim_employee WHERE employee_no = %s", (employee_no,))
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# POST /api/v1/customers  -  Create customer
# ---------------------------------------------------------------------------

@router.post("/customers")
async def create_customer(request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    branch_code = body.get("branch_code")
    body_channel_code = body.get("channel_code")
    customer_type = body.get("customer_type", "personal")
    customer_name = body.get("customer_name")

    # Look up branch_id
    branch = fetch_one(
        "SELECT id FROM dim_branch WHERE branch_code = %s",
        (branch_code,),
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    branch_id = branch["id"]

    # Look up register_channel_id from X-Channel-Code header
    channel = fetch_one(
        "SELECT id FROM dim_channel WHERE channel_code = %s",
        (channel_code,),
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    register_channel_id = channel["id"]

    # Look up default risk_level_id
    risk_level = fetch_one(
        "SELECT id FROM dim_risk_level WHERE yn = 1 AND risk_level_type = 'customer' ORDER BY sort_no LIMIT 1"
    )
    risk_level_id = risk_level["id"] if risk_level else None

    # Generate customer_no
    customer_no = gen_no("CUS")

    # Insert customer
    now = datetime.now()
    customer_id = insert(
        """
        INSERT INTO customer
            (customer_no, customer_type, customer_name, branch_id, register_channel_id,
             risk_level_id, customer_status, opened_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s, %s)
        """,
        (customer_no, customer_type, customer_name, branch_id, register_channel_id,
         risk_level_id, now, now, now),
    )

    # Insert customer_status_history
    emp_id = _resolve_employee_id(operator_no)
    insert(
        """
        INSERT INTO customer_status_history
            (customer_id, change_seq, from_status, to_status, change_reason,
             related_type, related_id, operator_id, changed_at, created_at)
        VALUES (%s, 1, 'none', 'active', '开户注册', 'none', NULL, %s, %s, %s)
        """,
        (customer_id, emp_id, now, now),
    )

    # If enterprise, also insert into enterprise_profile
    if customer_type == "enterprise":
        insert(
            """
            INSERT INTO enterprise_profile
                (customer_id, company_name, uniform_social_credit_code,
                 registered_capital_amount, registered_capital_currency_code,
                 established_date, registered_address, business_scope, industry,
                 business_status, compliance_status,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'normal', 'compliant', %s, %s)
            """,
            (
                customer_id,
                body.get("company_name"),
                body.get("uniform_social_credit_code"),
                body.get("registered_capital_amount"),
                body.get("registered_capital_currency_code"),
                body.get("established_date"),
                body.get("registered_address"),
                body.get("business_scope"),
                body.get("industry"),
                now,
                now,
            ),
        )

    response_data = {"customer_no": customer_no}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}  -  Get customer profile
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}")
async def get_customer(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT * FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    enterprise = fetch_one(
        "SELECT * FROM enterprise_profile WHERE customer_id = %s",
        (customer["id"],),
    )

    return ok({
        "customer_profile": _serialize(customer),
        "enterprise_profile": _serialize(enterprise) if enterprise else None,
    })


# ---------------------------------------------------------------------------
# PATCH /api/v1/customers/{customer_no}  -  Update customer
# ---------------------------------------------------------------------------

@router.patch("/customers/{customer_no}")
async def update_customer(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT * FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_name = body.get("customer_name")
    branch_code = body.get("branch_code")

    # Look up branch_id
    branch = fetch_one(
        "SELECT id FROM dim_branch WHERE branch_code = %s",
        (branch_code,),
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    branch_id = branch["id"]

    # Update customer
    execute(
        "UPDATE customer SET customer_name = %s, branch_id = %s, updated_at = %s WHERE id = %s",
        (customer_name, branch_id, datetime.now(), customer["id"]),
    )

    # Insert status_history
    now = datetime.now()
    emp_id = _resolve_employee_id(operator_no)
    insert(
        """
        INSERT INTO customer_status_history
            (customer_id, change_seq, from_status, to_status, change_reason,
             related_type, related_id, operator_id, changed_at, created_at)
        VALUES (%s, 2, %s, %s, '信息更新', 'none', NULL, %s, %s, %s)
        """,
        (customer["id"], customer["customer_status"], customer["customer_status"],
         emp_id, now, now),
    )

    response_data = {"customer_no": customer_no}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/identities  -  Add identity
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/identities")
async def add_identity(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Set existing current identity to 0
    execute(
        "UPDATE customer_identity SET current_flag = 0 WHERE customer_id = %s AND current_flag = 1",
        (customer["id"],),
    )

    now = datetime.now()
    insert(
        """
        INSERT INTO customer_identity
            (customer_id, identity_type, identity_no, legal_name,
             identity_valid_from, identity_valid_to, verification_status,
             current_flag, verified_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'verified', 1, %s, %s, %s)
        """,
        (
            customer["id"],
            body.get("identity_type"),
            body.get("identity_no"),
            body.get("legal_name"),
            body.get("identity_valid_from"),
            body.get("identity_valid_to"),
            now, now, now,
        ),
    )

    response_data = {"identity_id": customer["id"]}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/contacts  -  Add contact
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/contacts")
async def add_contact(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now()
    contact_id = insert(
        """
        INSERT INTO customer_contact
            (customer_id, contact_type, contact_value, contact_name,
             is_primary, verified_flag, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
        """,
        (
            customer["id"],
            body.get("contact_type"),
            body.get("contact_value"),
            body.get("contact_name"),
            body.get("is_primary"),
            now, now,
        ),
    )

    response_data = {"contact_id": contact_id}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/devices  -  Register device
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/devices")
async def register_device(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now()
    device_no = gen_no("DEV")
    device_id = insert(
        """
        INSERT INTO customer_device
            (device_no, customer_id, device_type, device_fingerprint,
             push_token, device_name, risk_status, first_seen_at,
             last_seen_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'trusted', %s, %s, %s, %s)
        """,
        (
            device_no,
            customer["id"],
            body.get("device_type"),
            body.get("device_fingerprint"),
            body.get("push_token"),
            body.get("device_name"),
            now, now, now, now,
        ),
    )

    response_data = {"device_id": device_id, "device_no": device_no}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/kyc  -  Submit KYC
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/kyc")
async def submit_kyc(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now()
    kyc_id = insert(
        """
        INSERT INTO customer_kyc
            (customer_id, occupation, industry, annual_income_amount,
             income_currency_code, fund_source, employment_status,
             kyc_status, compliance_status, review_result,
             reviewed_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed', 'passed', 'approved', %s, %s, %s)
        """,
        (
            customer["id"],
            body.get("occupation"),
            body.get("industry"),
            body.get("annual_income_amount"),
            body.get("income_currency_code"),
            body.get("fund_source"),
            body.get("employment_status"),
            now, now, now,
        ),
    )

    response_data = {"kyc_id": kyc_id}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/beneficial-owners  -  Add beneficial owner
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/beneficial-owners")
async def add_beneficial_owner(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now()
    owner_id = insert(
        """
        INSERT INTO beneficial_owner
            (customer_id, owner_type, owner_name, identity_type, identity_no,
             ownership_ratio, control_description,
             authorization_valid_from, authorization_valid_to,
             created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            customer["id"],
            body.get("owner_type"),
            body.get("owner_name"),
            body.get("identity_type"),
            body.get("identity_no"),
            body.get("ownership_ratio"),
            body.get("control_description"),
            body.get("authorization_valid_from"),
            body.get("authorization_valid_to"),
            now, now,
        ),
    )

    response_data = {"owner_id": owner_id}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/risk-assessments  -  Create risk assessment
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/risk-assessments")
async def create_risk_assessment(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    assessment_score = body.get("assessment_score", 0)

    # Look up risk_level_id based on score
    risk_levels = fetch_all(
        "SELECT id FROM dim_risk_level WHERE yn = 1 AND risk_level_type = 'customer' ORDER BY sort_no"
    )
    risk_level_id = None
    if risk_levels:
        idx = int(assessment_score) % len(risk_levels)
        risk_level_id = risk_levels[idx]["id"]

    assessment_no = gen_no("CRA")
    now = datetime.now()
    emp_id = _resolve_employee_id(operator_no)
    assessment_id = insert(
        """
        INSERT INTO customer_risk_assessment
            (assessment_no, customer_id, risk_level_id, assessment_score,
             assessment_type, assessment_status, valid_from, valid_to,
             operator_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'valid', %s, %s, %s, %s, %s)
        """,
        (
            assessment_no,
            customer["id"],
            risk_level_id,
            assessment_score,
            body.get("assessment_type"),
            body.get("valid_from"),
            body.get("valid_to"),
            emp_id,
            now, now,
        ),
    )

    response_data = {"assessment_id": assessment_id, "assessment_no": assessment_no}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{customer_no}/tags  -  Add tag
# ---------------------------------------------------------------------------

@router.post("/customers/{customer_no}/tags")
async def add_tag(customer_no: str, request: Request):
    body = await request.json()
    request_no, channel_code, operator_no, payload = _idempotency_params(request, body)

    existing = check_idempotency(request_no, channel_code, operator_no, payload)
    if existing is not None:
        return ok(existing)

    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    tag_code = body.get("tag_code")
    tag = fetch_one(
        "SELECT id FROM customer_tag WHERE tag_code = %s",
        (tag_code,),
    )
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    now = datetime.now()
    today = date.today()
    rel_id = insert(
        """
        INSERT INTO customer_tag_rel
            (customer_id, tag_id, source_type, effective_from, effective_to, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (customer["id"], tag["id"], body.get("source_type"), today, today, now),
    )

    response_data = {"tag_rel_id": rel_id}
    record_request(request_no, channel_code, operator_no, payload, response_data)
    return ok(response_data)


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}/status-history
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}/status-history")
async def get_status_history(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = fetch_all(
        """
        SELECT * FROM customer_status_history
        WHERE customer_id = %s
        ORDER BY change_seq
        """,
        (customer["id"],),
    )
    return list_ok(_serialize(rows))


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}/accounts
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}/accounts")
async def get_customer_accounts(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = fetch_all(
        "SELECT * FROM bank_account WHERE customer_id = %s",
        (customer["id"],),
    )
    return list_ok(_serialize(rows))


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}/wealth/positions
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}/wealth/positions")
async def get_wealth_positions(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = fetch_all(
        "SELECT * FROM wealth_position WHERE customer_id = %s",
        (customer["id"],),
    )
    return list_ok(_serialize(rows))


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}/wealth/incomes
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}/wealth/incomes")
async def get_wealth_incomes(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = fetch_all(
        "SELECT * FROM wealth_income WHERE customer_id = %s",
        (customer["id"],),
    )
    return list_ok(_serialize(rows), total_count=len(rows))


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}/credit-limits
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}/credit-limits")
async def get_credit_limits(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = fetch_all(
        "SELECT * FROM credit_limit WHERE customer_id = %s",
        (customer["id"],),
    )
    return list_ok(_serialize(rows))


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_no}/notifications
# ---------------------------------------------------------------------------

@router.get("/customers/{customer_no}/notifications")
async def get_notifications(customer_no: str, request: Request):
    _check_auth(request, customer_no)

    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s",
        (customer_no,),
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = fetch_all(
        "SELECT * FROM notification_message WHERE customer_id = %s",
        (customer["id"],),
    )
    return list_ok(_serialize(rows), total_count=len(rows))
