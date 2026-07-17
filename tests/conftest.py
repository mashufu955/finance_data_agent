"""Shared integration test fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database import db_cursor, fetch_one
from app.idempotency import _RECORDS
from app.main import app

# Import shared helpers -- these live in tests/_shared.py to avoid the
# conftest shadowing problem with tests/test_agent/conftest.py.
from tests._shared import (
    ApiClient,
    create_account,
    create_customer,
    delete_rows_after,
    insert_collateral,
    insert_contract_document,
    make_first_bill_overdue,
    prepare_wealth_open_period,
    require_seed,
    table_max_ids,
)

# Re-export for backwards compatibility (test files that do `from conftest import ...`)
__all__ = [
    "ApiClient",
    "create_account",
    "create_customer",
    "delete_rows_after",
    "insert_collateral",
    "insert_contract_document",
    "make_first_bill_overdue",
    "prepare_wealth_open_period",
    "require_seed",
    "table_max_ids",
]


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def seed() -> dict[str, Any]:
    return {
        "channel_code": require_seed(
            "SELECT channel_code FROM dim_channel WHERE channel_status = 'active' LIMIT 1"
        )["channel_code"],
        "employee_no": require_seed(
            "SELECT employee_no FROM dim_employee WHERE employee_status = 'active' LIMIT 1"
        )["employee_no"],
        "collector_no": require_seed(
            """
            SELECT employee_no
            FROM dim_employee
            WHERE employee_status = 'active' AND employee_role = 'collector'
            LIMIT 1
            """
        )["employee_no"],
        "branch_code": require_seed(
            "SELECT branch_code FROM dim_branch WHERE branch_status = 'active' LIMIT 1"
        )["branch_code"],
        "account_product": require_seed(
            """
            SELECT product_code, currency_code
            FROM account_product
            WHERE product_status = 'active' AND currency_code = 'CNY'
            LIMIT 1
            """
        ),
        "loan_product": require_seed(
            """
            SELECT product_code, min_amount, max_amount, min_term_months,
                   max_term_months, annual_interest_rate, repayment_method
            FROM loan_product
            WHERE product_status = 'active' AND currency_code = 'CNY'
            LIMIT 1
            """
        ),
        "wealth_product": require_seed(
            """
            SELECT id, product_code, min_purchase_amount
            FROM wealth_product
            WHERE product_status IN ('selling', 'active') AND currency_code = 'CNY'
            LIMIT 1
            """
        ),
        "risk_level_code": require_seed(
            """
            SELECT risk_level_code
            FROM dim_risk_level
            WHERE yn = 1 AND risk_level_type = 'event'
            ORDER BY sort_no
            LIMIT 1
            """
        )["risk_level_code"],
        "risk_event_type": require_seed(
            """
            SELECT applicable_event_type
            FROM risk_strategy
            WHERE strategy_status = 'active'
            LIMIT 1
            """
        )["applicable_event_type"],
    }


@pytest.fixture(autouse=True)
def isolated_database() -> Iterator[None]:
    # customer_tag is a program-generated table (no seed SQL); ensure a row exists
    # BEFORE recording max IDs so it's included in the baseline.
    existing = fetch_one("SELECT tag_code FROM customer_tag WHERE yn = 1 LIMIT 1")
    if existing is None:
        from datetime import datetime
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO customer_tag
                    (tag_code, tag_name, tag_type, yn, created_at, updated_at)
                VALUES (%s, %s, %s, 1, %s, %s)
                """,
                ("TEST_TAG", "test tag", "segmentation", datetime.now(), datetime.now()),
            )

    before = table_max_ids()
    _RECORDS.clear()
    try:
        yield
    finally:
        _RECORDS.clear()
        delete_rows_after(before)


@pytest.fixture
def api(client: TestClient, seed: dict[str, Any]) -> ApiClient:
    return ApiClient(client, seed)
