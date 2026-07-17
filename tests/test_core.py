"""Tests for core infrastructure: context, middleware, lifespan, logging."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.context import request_id_ctx_var


class TestContext:
    def test_request_id_ctx_var_default(self):
        """ContextVar starts without a value in each new context."""
        with pytest.raises(LookupError):
            request_id_ctx_var.get()

    def test_request_id_ctx_var_set_and_get(self):
        token = request_id_ctx_var.set("test-id-123")
        try:
            assert request_id_ctx_var.get() == "test-id-123"
        finally:
            request_id_ctx_var.reset(token)


class TestRequestIDMiddleware:
    def test_generates_request_id_when_missing(self):
        from app.core.middleware import RequestIDMiddleware

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        app.add_middleware(RequestIDMiddleware)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_preserves_existing_request_id(self):
        from app.core.middleware import RequestIDMiddleware

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        app.add_middleware(RequestIDMiddleware)
        client = TestClient(app)
        custom_id = "my-custom-id-42"
        response = client.get("/test", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id

    def test_sets_request_id_in_context_var(self):
        from app.core.middleware import RequestIDMiddleware

        captured_id = None

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            nonlocal captured_id
            captured_id = request_id_ctx_var.get()
            return {"ok": True}

        app.add_middleware(RequestIDMiddleware)
        client = TestClient(app)
        custom_id = "ctx-var-check-id"
        client.get("/test", headers={"X-Request-ID": custom_id})
        assert captured_id == custom_id


class TestLifespan:
    @pytest.mark.asyncio
    @patch("app.core.lifespan.embedding_client_manager", new_callable=AsyncMock)
    @patch("app.core.lifespan.qdrant_client_manager", new_callable=AsyncMock)
    @patch("app.core.lifespan.es_client_manager", new_callable=AsyncMock)
    @patch("app.core.lifespan.meta_client_manager", new_callable=AsyncMock)
    @patch("app.core.lifespan.dw_client_manager", new_callable=AsyncMock)
    async def test_lifespan_init_and_close(self, mock_dw, mock_meta, mock_es, mock_qdrant, mock_emb):
        from app.core.lifespan import lifespan

        app = FastAPI()
        ctx = lifespan(app)
        await ctx.__aenter__()
        mock_dw.init.assert_called_once()
        mock_meta.init.assert_called_once()
        mock_es.init.assert_called_once()
        mock_qdrant.init.assert_called_once()
        mock_emb.init.assert_called_once()
        await ctx.__aexit__(None, None, None)
        mock_dw.close.assert_called_once()
        mock_meta.close.assert_called_once()
        mock_es.close.assert_called_once()
        mock_qdrant.close.assert_called_once()
