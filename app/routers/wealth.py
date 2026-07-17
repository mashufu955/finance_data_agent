"""Wealth management endpoints."""

from __future__ import annotations

import datetime
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.database import execute, fetch_all, fetch_one, insert
from app.idempotency import check_idempotency, record_request
from app.response import list_ok, ok

router = APIRouter(tags=["wealth"])

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
# 1. GET /api/v1/wealth/products
# ---------------------------------------------------------------------------

@router.get("/api/v1/wealth/products")
def list_wealth_products(currency_code: str = Query(None)):
    if currency_code:
        rows = fetch_all(
            "SELECT * FROM wealth_product WHERE product_status IN ('selling','active') AND currency_code = %s",
            (currency_code,),
        )
    else:
        rows = fetch_all(
            "SELECT * FROM wealth_product WHERE product_status IN ('selling','active')"
        )
    return list_ok(_ser(rows), total_count=len(rows))


# ---------------------------------------------------------------------------
# 2. GET /api/v1/wealth/products/{product_code}
# ---------------------------------------------------------------------------

@router.get("/api/v1/wealth/products/{product_code}")
def get_wealth_product(product_code: str):
    row = fetch_one(
        "SELECT * FROM wealth_product WHERE product_code = %s", (product_code,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Wealth product not found")
    return ok(_ser(row))


# ---------------------------------------------------------------------------
# 3. GET /api/v1/wealth/products/{product_code}/navs
# ---------------------------------------------------------------------------

@router.get("/api/v1/wealth/products/{product_code}/navs")
def get_wealth_navs(product_code: str, page_size: int = Query(20)):
    navs = fetch_all(
        "SELECT wn.* FROM wealth_nav wn "
        "JOIN wealth_product wp ON wn.product_id = wp.id "
        "WHERE wp.product_code = %s "
        "ORDER BY wn.nav_date DESC LIMIT %s",
        (product_code, page_size),
    )
    count_row = fetch_one(
        "SELECT COUNT(*) AS cnt FROM wealth_nav wn "
        "JOIN wealth_product wp ON wn.product_id = wp.id "
        "WHERE wp.product_code = %s",
        (product_code,),
    )
    total_count = count_row["cnt"] if count_row else 0
    return list_ok(_ser(navs), total_count=total_count)


# ---------------------------------------------------------------------------
# 4. POST /api/v1/wealth/orders/purchase
# ---------------------------------------------------------------------------

@router.post("/api/v1/wealth/orders/purchase")
async def purchase_wealth_product(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    customer_no = body["customer_no"]
    account_no = body["account_no"]
    product_code = body["product_code"]
    purchase_amount = Decimal(str(body["purchase_amount"]))

    # -- look-ups --
    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s", (customer_no,)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    account = fetch_one(
        "SELECT id, currency_code, open_channel_id FROM bank_account WHERE account_no = %s", (account_no,)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]
    currency_code = account["currency_code"]
    channel_id = account["open_channel_id"]

    product = fetch_one(
        "SELECT id FROM wealth_product WHERE product_code = %s", (product_code,)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Wealth product not found")
    product_id = product["id"]

    # -- latest NAV --
    nav_row = fetch_one(
        "SELECT unit_nav FROM wealth_nav WHERE product_id = %s ORDER BY nav_date DESC LIMIT 1",
        (product_id,),
    )
    unit_nav = Decimal(str(nav_row["unit_nav"])) if nav_row else Decimal("1")
    shares = (purchase_amount / unit_nav).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )

    order_no = gen_no("WO")

    # -- create / update wealth_position --
    position = fetch_one(
        "SELECT id, available_share, holding_share FROM wealth_position "
        "WHERE customer_id = %s AND account_id = %s AND product_id = %s",
        (customer_id, account_id, product_id),
    )
    now = datetime.datetime.now()
    if position:
        execute(
            "UPDATE wealth_position SET available_share = available_share + %s, "
            "holding_share = holding_share + %s, updated_at = %s WHERE id = %s",
            (shares, shares, now, position["id"]),
        )
        position_id = position["id"]
    else:
        position_id = insert(
            "INSERT INTO wealth_position "
            "(customer_id, account_id, product_id, currency_code, available_share, "
            "holding_share, frozen_share, cost_amount, market_value_amount, "
            "accumulated_income_amount, last_nav, last_valuation_date, position_status, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, 0, 1, %s, 'active', %s, %s)",
            (customer_id, account_id, product_id, currency_code, shares, shares,
             now.date(), now, now),
        )

    # -- insert wealth_order --
    order_id = insert(
        "INSERT INTO wealth_order "
        "(order_no, customer_id, account_id, product_id, channel_id, order_type, order_status, "
        "currency_code, order_amount, order_share, confirmed_amount, confirmed_share, "
        "fee_amount, submitted_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, %s, %s)",
        (
            order_no, customer_id, account_id, product_id, channel_id,
            "purchase", "submitted", currency_code, purchase_amount, shares,
            now, now, now,
        ),
    )

    # -- account transaction (debit) --
    txn_no = gen_no("TXN")
    insert(
        "INSERT INTO account_transaction "
        "(transaction_no, customer_id, from_account_id, channel_id, transaction_type, "
        "transaction_status, reconcile_status, currency_code, transaction_amount, "
        "related_type, transaction_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (txn_no, customer_id, account_id, channel_id, "payment",
         "success", "pending", currency_code, purchase_amount,
         "wealth_purchase", now, now, now),
    )

    order = fetch_one("SELECT * FROM wealth_order WHERE id = %s", (order_id,))
    result = _ser(order)
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 5. POST /api/v1/wealth/orders/{order_no}/confirm
# ---------------------------------------------------------------------------

@router.post("/api/v1/wealth/orders/{order_no}/confirm")
async def confirm_wealth_order(order_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    execute(
        "UPDATE wealth_order SET order_status = %s, "
        "confirmed_amount = %s, confirmed_share = %s, confirmed_nav = %s, "
        "confirmed_at = NOW() WHERE order_no = %s",
        (
            "confirmed",
            body.get("confirmed_amount"),
            body.get("confirmed_share"),
            body.get("confirmed_nav"),
            order_no,
        ),
    )
    order = fetch_one("SELECT * FROM wealth_order WHERE order_no = %s", (order_no,))
    result = _ser(order)
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 6. POST /api/v1/wealth/orders/{order_no}/cancel
# ---------------------------------------------------------------------------

@router.post("/api/v1/wealth/orders/{order_no}/cancel")
async def cancel_wealth_order(order_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    execute(
        "UPDATE wealth_order SET order_status = %s, "
        "cancel_reason = %s, cancelled_at = NOW() WHERE order_no = %s",
        ("cancelled", body.get("cancel_reason", ""), order_no),
    )
    order = fetch_one("SELECT * FROM wealth_order WHERE order_no = %s", (order_no,))
    result = _ser(order)
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 7. GET /api/v1/wealth/orders/{order_no}
# ---------------------------------------------------------------------------

@router.get("/api/v1/wealth/orders/{order_no}")
def get_wealth_order(order_no: str):
    order = fetch_one("SELECT * FROM wealth_order WHERE order_no = %s", (order_no,))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return ok(_ser(order))


# ---------------------------------------------------------------------------
# 8. POST /api/v1/wealth/orders/redeem
# ---------------------------------------------------------------------------

@router.post("/api/v1/wealth/orders/redeem")
async def redeem_wealth_order(request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    customer_no = body["customer_no"]
    account_no = body["account_no"]
    position_id = body["position_id"]
    redeem_share = Decimal(str(body["redeem_share"]))

    # -- look-ups --
    customer = fetch_one(
        "SELECT id FROM customer WHERE customer_no = %s", (customer_no,)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer_id = customer["id"]

    account = fetch_one(
        "SELECT id, currency_code, open_channel_id FROM bank_account WHERE account_no = %s", (account_no,)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account_id = account["id"]
    currency_code = account["currency_code"]
    channel_id = account["open_channel_id"]

    position = fetch_one(
        "SELECT * FROM wealth_position WHERE id = %s", (position_id,)
    )
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    product_id = position["product_id"]

    # -- latest NAV for redeem amount --
    nav_row = fetch_one(
        "SELECT unit_nav FROM wealth_nav WHERE product_id = %s ORDER BY nav_date DESC LIMIT 1",
        (product_id,),
    )
    unit_nav = Decimal(str(nav_row["unit_nav"])) if nav_row else Decimal("1")
    redeem_amount = redeem_share * unit_nav

    order_no = gen_no("WO")

    # -- decrease available_share --
    execute(
        "UPDATE wealth_position SET available_share = available_share - %s "
        "WHERE id = %s",
        (redeem_share, position_id),
    )

    # -- insert wealth_order --
    now = datetime.datetime.now()
    order_id = insert(
        "INSERT INTO wealth_order "
        "(order_no, customer_id, account_id, product_id, channel_id, order_type, order_status, "
        "currency_code, order_amount, order_share, confirmed_amount, confirmed_share, "
        "fee_amount, submitted_at, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, %s, %s)",
        (
            order_no, customer_id, account_id, product_id, channel_id,
            "redeem", "submitted", currency_code, redeem_amount, redeem_share,
            now, now, now,
        ),
    )

    order = fetch_one("SELECT * FROM wealth_order WHERE id = %s", (order_id,))
    result = _ser(order)
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp


# ---------------------------------------------------------------------------
# 9. POST /api/v1/wealth/incomes/{income_no}/settle
# ---------------------------------------------------------------------------

@router.post("/api/v1/wealth/incomes/{income_no}/settle")
async def settle_wealth_income(income_no: str, request: Request):
    body = await request.json()
    rn, ch, op = _idem_key(request, body)
    dup = check_idempotency(rn, ch, op, body)
    if dup is not None:
        return dup

    execute(
        "UPDATE wealth_income SET settled_flag = 1, settled_at = NOW() "
        "WHERE income_no = %s",
        (income_no,),
    )

    result = {"settled_flag": 1}
    resp = ok(result)
    record_request(rn, ch, op, body, resp)
    return resp
