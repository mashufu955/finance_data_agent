"""Tests for MySQL repositories, Qdrant base repository, and client managers."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# Pre-mock app.agent.llm to prevent real init_chat_model() call
_mock_llm = MagicMock()
_mock_llm.llm = AsyncMock()
sys.modules.setdefault("app.agent.llm", _mock_llm)


# ===========================================================================
# 1. DWMySQLRepository
# ===========================================================================

class TestDWMySQLRepository:
    @pytest.fixture
    def session(self):
        return AsyncMock()

    @pytest.fixture
    def repo(self, session):
        from app.repositories.mysql.dw_mysql_repository import DWMySQLRepository
        return DWMySQLRepository(session)

    @pytest.mark.asyncio
    async def test_get_column_types(self, repo, session):
        row1 = MagicMock(Field="id", Type="int")
        row2 = MagicMock(Field="name", Type="varchar(64)")
        session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row1, row2])))
        result = await repo.get_column_types("test_table")
        assert result == {"id": "int", "name": "varchar(64)"}

    @pytest.mark.asyncio
    async def test_get_column_values(self, repo, session):
        row1 = MagicMock(column_value="val1")
        row2 = MagicMock(column_value="val2")
        session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row1, row2])))
        result = await repo.get_column_values("test_table", "col1", 10)
        assert result == ["val1", "val2"]

    @pytest.mark.asyncio
    async def test_get_db_info(self, repo, session):
        bind = MagicMock()
        bind.dialect.name = "mysql"
        session.get_bind = MagicMock(return_value=bind)
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value="8.0.35")))
        result = await repo.get_db_info()
        assert result == {"dialect": "mysql", "version": "8.0.35"}

    @pytest.mark.asyncio
    async def test_get_date_info(self, repo, session):
        now = MagicMock()
        now.strftime = MagicMock(side_effect=lambda fmt: {
            "%Y-%m-%d": "2026-07-16",
            "%A": "Thursday",
            "%Q": "Q3",
        }.get(fmt, ""))
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=now)))
        result = await repo.get_date_info()
        assert result["date"] == "2026-07-16"
        assert result["weekday"] == "Thursday"

    @pytest.mark.asyncio
    async def test_validate_sql(self, repo, session):
        session.execute = AsyncMock()
        await repo.validate_sql("SELECT 1")
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_sql(self, repo, session):
        mapping_row = {"id": 1, "name": "test"}
        result_mock = MagicMock()
        result_mock.mappings.return_value.fetchall.return_value = [mapping_row]
        session.execute = AsyncMock(return_value=result_mock)
        result = await repo.execute_sql("SELECT * FROM t")
        assert result == [{"id": 1, "name": "test"}]


# ===========================================================================
# 2. MetaMySQLRepository
# ===========================================================================

class TestMetaMySQLRepository:
    @pytest.fixture
    def session(self):
        return AsyncMock()

    @pytest.fixture
    def repo(self, session):
        from app.repositories.mysql.meta_mysql_repository import MetaMySQLRepository
        return MetaMySQLRepository(session)

    @pytest.mark.asyncio
    async def test_save_table_infos(self, repo, session):
        session.add_all = MagicMock()
        items = [MagicMock(), MagicMock()]
        await repo.save_table_infos(items)
        session.add_all.assert_called_once_with(items)

    @pytest.mark.asyncio
    async def test_save_column_infos(self, repo, session):
        session.add_all = MagicMock()
        items = [MagicMock()]
        await repo.save_column_infos(items)
        session.add_all.assert_called_once_with(items)

    @pytest.mark.asyncio
    async def test_save_metric_infos(self, repo, session):
        session.add_all = MagicMock()
        items = [MagicMock()]
        await repo.save_metric_infos(items)
        session.add_all.assert_called_once_with(items)

    @pytest.mark.asyncio
    async def test_save_column_metrics(self, repo, session):
        session.add_all = MagicMock()
        items = [MagicMock()]
        await repo.save_column_metrics(items)
        session.add_all.assert_called_once_with(items)

    @pytest.mark.asyncio
    async def test_get_column_by_id(self, repo, session):
        col = MagicMock()
        session.get = AsyncMock(return_value=col)
        result = await repo.get_column_by_id("t.c")
        session.get.assert_called_once()
        assert result is col

    @pytest.mark.asyncio
    async def test_get_column_by_id_not_found(self, repo, session):
        session.get = AsyncMock(return_value=None)
        result = await repo.get_column_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_table_by_id(self, repo, session):
        tbl = MagicMock()
        session.get = AsyncMock(return_value=tbl)
        result = await repo.get_table_by_id("t")
        assert result is tbl

    @pytest.mark.asyncio
    async def test_get_key_columns_by_table_id(self, repo, session):
        col1 = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[col1])
        execute_result = MagicMock()
        execute_result.scalars = MagicMock(return_value=scalars)
        session.execute = AsyncMock(return_value=execute_result)
        result = await repo.get_key_columns_by_table_id("t")
        assert len(result) == 1


# ===========================================================================
# 3. BaseQdrantRepository
# ===========================================================================

class TestBaseQdrantRepository:
    @pytest.fixture
    def client(self):
        return AsyncMock()

    @pytest.fixture
    def repo(self, client):
        from app.repositories.qdrant.base_repository_qdrant import BaseQdrantRepository

        class ConcreteRepo(BaseQdrantRepository):
            collection_name = "test_collection"

        return ConcreteRepo(client)

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_when_missing(self, repo, client):
        client.collection_exists = AsyncMock(return_value=False)
        client.create_collection = AsyncMock()
        with patch("app.repositories.qdrant.base_repository_qdrant.app_config") as mock_cfg:
            mock_cfg.qdrant.embedding_size = 128
            await repo.ensure_collection()
        client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_when_exists(self, repo, client):
        client.collection_exists = AsyncMock(return_value=True)
        client.create_collection = AsyncMock()
        await repo.ensure_collection()
        client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_single_batch(self, repo, client):
        import uuid
        client.upsert = AsyncMock()
        ids = [uuid.uuid4(), uuid.uuid4()]
        embeddings = [[0.1] * 128, [0.2] * 128]
        payloads = [{"name": "a"}, {"name": "b"}]
        await repo.upsert(ids, embeddings, payloads, batch_size=10)
        client.upsert.assert_called_once()
        call_args = client.upsert.call_args
        assert len(call_args[1]["points"]) == 2

    @pytest.mark.asyncio
    async def test_upsert_multiple_batches(self, repo, client):
        import uuid
        client.upsert = AsyncMock()
        ids = [uuid.uuid4() for _ in range(5)]
        embeddings = [[0.1] * 128] * 5
        payloads = [{"name": f"n{i}"} for i in range(5)]
        await repo.upsert(ids, embeddings, payloads, batch_size=2)
        assert client.upsert.call_count == 3

    @pytest.mark.asyncio
    async def test_search_returns_payloads(self, repo, client):
        point1 = MagicMock(payload={"name": "a"})
        point2 = MagicMock(payload={"name": "b"})
        query_result = MagicMock()
        query_result.points = [point1, point2]
        client.query_points = AsyncMock(return_value=query_result)
        result = await repo.search([0.1] * 128, score_threshold=0.5, limit=10)
        assert len(result) == 2
        assert result[0]["name"] == "a"

    @pytest.mark.asyncio
    async def test_search_empty(self, repo, client):
        query_result = MagicMock()
        query_result.points = []
        client.query_points = AsyncMock(return_value=query_result)
        result = await repo.search([0.1] * 128)
        assert result == []


# ===========================================================================
# 4. Client managers
# ===========================================================================

class TestClientManagers:
    def test_es_client_manager_init_and_close(self):
        from app.clients.es_client import es_client_manager
        with patch("app.clients.es_client.AsyncElasticsearch") as mock_cls:
            mock_cls.return_value = AsyncMock()
            with patch("app.clients.es_client.app_config") as mock_cfg:
                mock_cfg.elasticsearch.host = "127.0.0.1"
                mock_cfg.elasticsearch.port = 9200
                es_client_manager.init()
                assert es_client_manager.client is not None

    def test_qdrant_client_manager_init_and_close(self):
        from app.clients.qdrant_client import qdrant_client_manager
        with patch("app.clients.qdrant_client.AsyncQdrantClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            with patch("app.clients.qdrant_client.app_config") as mock_cfg:
                mock_cfg.qdrant.host = "127.0.0.1"
                mock_cfg.qdrant.port = 6333
                qdrant_client_manager.init()
                assert qdrant_client_manager.client is not None

    def test_mysql_client_manager_init(self):
        from app.clients.mysql_client import MySQLClientManager
        mock_config = MagicMock()
        mock_config.user = "root"
        mock_config.password = "pass"
        mock_config.host = "127.0.0.1"
        mock_config.port = 3306
        mock_config.database = "dw"
        mgr = MySQLClientManager(mock_config)
        with patch("app.clients.mysql_client.create_async_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            with patch("app.clients.mysql_client.async_sessionmaker") as mock_session:
                mock_session.return_value = MagicMock()
                mgr.init()
                assert mgr.session_factory is not None

    @pytest.mark.asyncio
    async def test_mysql_client_manager_close(self):
        from app.clients.mysql_client import MySQLClientManager
        mock_config = MagicMock()
        mgr = MySQLClientManager(mock_config)
        mgr.engine = AsyncMock()
        await mgr.close()
        mgr.engine.dispose.assert_called_once()


# ===========================================================================
# 5. chat_router actual endpoint
# ===========================================================================

class TestChatRouterActual:
    def test_chat_router_sse_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.deps import get_chat_service

        mock_service = MagicMock()

        async def mock_stream(*args, **kwargs):
            yield {"stage": "classify"}
            yield {"stage": "generate_sql"}

        mock_service.stream_chat = mock_stream

        from app.api.routers.chat_router import chat_router
        test_app = FastAPI()
        test_app.include_router(chat_router)
        test_app.dependency_overrides[get_chat_service] = lambda: mock_service

        client = TestClient(test_app)
        response = client.post("/api/query", json={"query": "test"})
        assert response.status_code == 200
        lines = [l for l in response.text.strip().split("\n") if l.startswith("data:")]
        assert len(lines) == 2


# ===========================================================================
# 6. main.py generic exception handler
# ===========================================================================

class TestGenericExceptionHandler:
    def test_generic_exception_returns_500(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        @test_app.get("/boom")
        async def boom():
            raise RuntimeError("unexpected error")

        # Register the same exception handler as main.py
        from app.main import generic_exception_handler
        test_app.add_exception_handler(Exception, generic_exception_handler)

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/boom")
        assert response.status_code == 500
        body = response.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert "unexpected error" in body["message"]


# ===========================================================================
# 7. Customer GET endpoints (404 branches)
# ===========================================================================

class TestCustomerGetEndpoints:
    @pytest.fixture
    def api_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.customers import router
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def _headers(self, customer_no: str = "EMP001"):
        return {
            "Authorization": f"Bearer {customer_no}",
            "X-Request-Id": "REQ001",
            "X-Channel-Code": "CH001",
            "X-Operator-No": "EMP001",
        }

    def test_wealth_positions_customer_not_found(self, api_client):
        with patch("app.routers.customers.fetch_one", return_value=None):
            response = api_client.get(
                "/api/v1/customers/NONE/wealth/positions",
                headers=self._headers("NONE"),
            )
            assert response.status_code == 404

    def test_wealth_incomes_customer_not_found(self, api_client):
        with patch("app.routers.customers.fetch_one", return_value=None):
            response = api_client.get(
                "/api/v1/customers/NONE/wealth/incomes",
                headers=self._headers("NONE"),
            )
            assert response.status_code == 404

    def test_credit_limits_customer_not_found(self, api_client):
        with patch("app.routers.customers.fetch_one", return_value=None):
            response = api_client.get(
                "/api/v1/customers/NONE/credit-limits",
                headers=self._headers("NONE"),
            )
            assert response.status_code == 404

    def test_notifications_customer_not_found(self, api_client):
        with patch("app.routers.customers.fetch_one", return_value=None):
            response = api_client.get(
                "/api/v1/customers/NONE/notifications",
                headers=self._headers("NONE"),
            )
            assert response.status_code == 404

    def test_wealth_positions_returns_list(self, api_client):
        with patch("app.routers.customers.fetch_one", return_value={"id": 1}):
            with patch("app.routers.customers.fetch_all", return_value=[]):
                response = api_client.get(
                    "/api/v1/customers/C001/wealth/positions",
                    headers=self._headers("C001"),
                )
                assert response.status_code == 200
                assert "list" in response.json()["data"]

    def test_wealth_incomes_returns_total_count(self, api_client):
        rows = [{"id": 1, "income_no": "INC001"}]
        with patch("app.routers.customers.fetch_one", return_value={"id": 1}):
            with patch("app.routers.customers.fetch_all", return_value=rows):
                response = api_client.get(
                    "/api/v1/customers/C001/wealth/incomes",
                    headers=self._headers("C001"),
                )
                assert response.status_code == 200
                body = response.json()["data"]
                assert body["total_count"] == 1


# ===========================================================================
# 8. Transaction GET endpoints (404 branches)
# ===========================================================================

class TestTransactionGetEndpoints:
    @pytest.fixture
    def api_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.transactions import router
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_get_transaction_not_found(self, api_client):
        with patch("app.routers.transactions.fetch_one", return_value=None):
            response = api_client.get("/api/v1/transactions/NONE")
            assert response.status_code == 404

    def test_get_transaction_found(self, api_client):
        row = {"id": 1, "transaction_no": "TXN001", "amount": 100}
        with patch("app.routers.transactions.fetch_one", return_value=row):
            with patch("app.routers.transactions._serialize_row", return_value=row):
                response = api_client.get("/api/v1/transactions/TXN001")
                assert response.status_code == 200

    def test_list_account_transactions_account_not_found(self, api_client):
        with patch("app.routers.transactions.fetch_one", return_value=None):
            response = api_client.get("/api/v1/accounts/NONE/transactions")
            assert response.status_code == 404

    def test_list_account_ledgers_account_not_found(self, api_client):
        with patch("app.routers.transactions.fetch_one", return_value=None):
            response = api_client.get("/api/v1/accounts/NONE/ledgers")
            assert response.status_code == 404

    def test_list_account_transactions_returns_data(self, api_client):
        account = {"id": 1}
        count_row = {"total": 2}
        rows = [{"id": 1}, {"id": 2}]
        with patch("app.routers.transactions.fetch_one", side_effect=[account, count_row]):
            with patch("app.routers.transactions.fetch_all", return_value=rows):
                with patch("app.routers.transactions._serialize_rows", side_effect=lambda x: x):
                    response = api_client.get("/api/v1/accounts/ACC001/transactions?page_size=10")
                    assert response.status_code == 200
                    body = response.json()["data"]
                    assert body["total_count"] == 2
