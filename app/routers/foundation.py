"""Foundation / catalog reference-data endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.database import fetch_all
from app.response import list_ok
from app.utils import serialize_list

router = APIRouter(prefix="/api/v1", tags=["foundation"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/branches")
def get_branches():
    rows = fetch_all(
        "SELECT * FROM dim_branch WHERE branch_status = %s",
        ("active",),
    )
    return list_ok(serialize_list(rows))


@router.get("/channels")
def get_channels():
    rows = fetch_all(
        "SELECT * FROM dim_channel WHERE channel_status = %s",
        ("active",),
    )
    return list_ok(serialize_list(rows))


@router.get("/currencies")
def get_currencies():
    rows = fetch_all(
        "SELECT * FROM dim_currency WHERE yn = %s",
        (1,),
    )
    return list_ok(serialize_list(rows))


@router.get("/risk-levels")
def get_risk_levels():
    rows = fetch_all(
        "SELECT * FROM dim_risk_level WHERE yn = %s",
        (1,),
    )
    return list_ok(serialize_list(rows))


@router.get("/account-products")
def get_account_products():
    rows = fetch_all(
        "SELECT * FROM account_product WHERE product_status = %s",
        ("active",),
    )
    return list_ok(serialize_list(rows))


@router.get("/service-products")
def get_service_products():
    rows = fetch_all(
        "SELECT * FROM service_product WHERE service_status = %s",
        ("active",),
    )
    return list_ok(serialize_list(rows))


@router.get("/employees")
def get_employees():
    rows = fetch_all(
        "SELECT * FROM dim_employee WHERE employee_status = %s",
        ("active",),
    )
    return list_ok(serialize_list(rows))
