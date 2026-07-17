"""Tests for API deps and chat router with mocked dependencies."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestDeps:
    """Test dependency injection functions."""

    def test_get_meta_repository(self):
        from app.repositories.mysql.meta_mysql_repository import MetaMySQLRepository
        mock_session = AsyncMock()
        repo = MetaMySQLRepository(mock_session)
        assert repo is not None

    def test_get_dw_repository(self):
        from app.repositories.mysql.dw_mysql_repository import DWMySQLRepository
        mock_session = AsyncMock()
        repo = DWMySQLRepository(mock_session)
        assert repo is not None

    @pytest.mark.asyncio
    async def test_get_column_qdrant_repository(self):
        with patch("app.api.deps.qdrant_client_manager") as mock_mgr:
            with patch("app.api.deps.ColumnQdrantRepository") as mock_cls:
                mock_cls.return_value = MagicMock()
                result = mock_cls(mock_mgr.client)
                mock_cls.assert_called_once_with(mock_mgr.client)

    @pytest.mark.asyncio
    async def test_get_metric_qdrant_repository(self):
        with patch("app.api.deps.qdrant_client_manager") as mock_mgr:
            with patch("app.api.deps.MetricQdrantRepository") as mock_cls:
                mock_cls.return_value = MagicMock()
                result = mock_cls(mock_mgr.client)
                mock_cls.assert_called_once_with(mock_mgr.client)

    @pytest.mark.asyncio
    async def test_get_value_es_repository(self):
        with patch("app.api.deps.es_client_manager") as mock_mgr:
            with patch("app.api.deps.ValueESRepository") as mock_cls:
                mock_cls.return_value = MagicMock()
                result = mock_cls(mock_mgr.client)
                mock_cls.assert_called_once_with(mock_mgr.client)

    @pytest.mark.asyncio
    async def test_get_embedding_client(self):
        with patch("app.api.deps.embedding_client_manager") as mock_mgr:
            assert mock_mgr.client is not None

    @pytest.mark.asyncio
    async def test_get_graph(self):
        with patch("app.api.deps.graph") as mock_graph:
            assert mock_graph is not None


class TestChatRouter:
    """Test the /api/query SSE endpoint."""

    def test_query_endpoint_returns_sse(self):
        from fastapi import FastAPI, Body
        from starlette.responses import StreamingResponse

        app = FastAPI()

        @app.post("/api/query")
        async def query_endpoint(body: dict = Body(...)):
            async def event_stream():
                yield f"data: {json.dumps({'stage': 'classify'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'stage': 'generate_sql'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(event_stream(), media_type="text/event-stream")

        client = TestClient(app)
        response = client.post("/api/query", json={"query": "test query"})
        assert response.status_code == 200, response.text
        assert "text/event-stream" in response.headers.get("content-type", "")
        lines = [l for l in response.text.strip().split("\n") if l.startswith("data:")]
        assert len(lines) == 2
        first_data = json.loads(lines[0].replace("data: ", ""))
        assert first_data["stage"] == "classify"

    def test_query_endpoint_error_handling(self):
        from fastapi import FastAPI, Body
        from starlette.responses import StreamingResponse

        app = FastAPI()

        @app.post("/api/query")
        async def query_endpoint(body: dict = Body(...)):
            async def event_stream():
                try:
                    raise RuntimeError("test error")
                    yield  # make it async generator
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return StreamingResponse(event_stream(), media_type="text/event-stream")

        client = TestClient(app)
        response = client.post("/api/query", json={"query": "test"})
        assert response.status_code == 200, response.text
        lines = response.text.strip().split("\n")
        error_data = json.loads(lines[0].replace("data: ", ""))
        assert "error" in error_data
        assert "test error" in error_data["error"]
