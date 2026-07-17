"""Shared fixtures for agent pipeline unit tests."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pre-mock app.agent.llm so that importing any node module does NOT trigger
# the real init_chat_model() call (which requires langchain-deepseek etc.)
# ---------------------------------------------------------------------------
_mock_llm_module = MagicMock()
_mock_llm_module.llm = AsyncMock()
sys.modules.setdefault("app.agent.llm", _mock_llm_module)


@pytest.fixture(autouse=True)
def isolated_database() -> None:
    """Override the parent conftest's autouse fixture -- agent tests need no real DB."""
    yield


@pytest.fixture
def mock_stream_writer():
    """Return a callable that records all stream writes."""
    writes: list[dict] = []

    def writer(data: dict):
        writes.append(data)

    writer.writes = writes
    return writer


@pytest.fixture
def mock_runtime(mock_stream_writer):
    """
    Build a mock LangGraph Runtime with all repository / client dependencies stubbed.
    Every repository method that nodes call is an AsyncMock returning sensible defaults.
    """
    runtime = MagicMock()
    runtime.stream_writer = mock_stream_writer

    # --- context dict ---
    ctx: dict[str, MagicMock] = {}

    # Qdrant: column recall
    column_qdrant = AsyncMock()
    column_qdrant.search = AsyncMock(return_value=[])
    ctx["column_qdrant_repository"] = column_qdrant

    # Qdrant: metric recall
    metric_qdrant = AsyncMock()
    metric_qdrant.search = AsyncMock(return_value=[])
    ctx["metric_qdrant_repository"] = metric_qdrant

    # ES: value recall
    value_es = AsyncMock()
    value_es.query = AsyncMock(return_value=[])
    ctx["value_es_repository"] = value_es

    # Embedding client
    embedding_client = AsyncMock()
    embedding_client.aembed_query = AsyncMock(return_value=[0.1] * 128)
    ctx["embedding_client"] = embedding_client

    # Meta MySQL repository
    meta_mysql = AsyncMock()
    meta_mysql.get_column_by_id = AsyncMock()
    meta_mysql.get_table_by_id = AsyncMock()
    meta_mysql.get_key_columns_by_table_id = AsyncMock(return_value=[])
    ctx["meta_mysql_repository"] = meta_mysql

    # DW MySQL repository
    dw_mysql = AsyncMock()
    dw_mysql.get_db_info = AsyncMock(return_value={"dialect": "mysql", "version": "8.0.0"})
    dw_mysql.execute_sql = AsyncMock(return_value=[])
    dw_mysql.validate_sql = AsyncMock(return_value=None)
    ctx["dw_mysql_repository"] = dw_mysql

    runtime.context = ctx
    return runtime


@pytest.fixture
def sample_column_qdrant():
    """A sample ColumnInfoQdrant record."""
    return {
        "id": "dw_customer.customer_name",
        "name": "customer_name",
        "type": "varchar(128)",
        "role": "dimension",
        "examples": ["Zhang San", "Li Si"],
        "description": "customer name",
        "alias": ["name"],
        "table_id": "dw_customer",
    }


@pytest.fixture
def sample_metric_qdrant():
    """A sample MetricInfoQdrant record."""
    return {
        "id": "\u65b0\u589e\u5ba2\u6237\u6570",
        "name": "\u65b0\u589e\u5ba2\u6237\u6570",
        "description": "\u7edf\u8ba1\u5468\u671f\u5185\u65b0\u6ce8\u518c\u7684\u5ba2\u6237\u6570\u91cf",
        "relevant_columns": ["dw_customer.id", "dw_customer.created_at"],
        "alias": ["\u65b0\u5ba2\u6570", "\u6ce8\u518c\u5ba2\u6237\u6570"],
    }


@pytest.fixture
def sample_value_es():
    """A sample ValueInfoES record."""
    return {
        "id": "dw_customer.risk_level.R1",
        "value": "R1",
        "type": "varchar",
        "column_id": "dw_customer.risk_level",
        "column_name": "risk_level",
        "table_id": "dw_customer",
        "table_name": "dw_customer",
    }


@pytest.fixture
def sample_column_mysql():
    """A sample ColumnInfoMySQL model object (mock)."""
    col = MagicMock()
    col.id = "dw_customer.risk_level"
    col.name = "risk_level"
    col.type = "varchar(32)"
    col.role = "dimension"
    col.examples = ["R1", "R2", "R3"]
    col.description = "risk level"
    col.alias = ["risk rating"]
    col.table_id = "dw_customer"
    return col


@pytest.fixture
def sample_table_mysql():
    """A sample TableInfoMySQL model object (mock)."""
    tbl = MagicMock()
    tbl.id = "dw_customer"
    tbl.name = "dw_customer"
    tbl.role = "fact"
    tbl.description = "customer info table"
    return tbl
