"""Embedding client using httpx to talk to a local TEI endpoint."""

from __future__ import annotations

import httpx

from app.clients.base import BaseClientManager
from app.config.app_config import app_config
from app.core.logging import logger


class LocalTEIEmbeddings:
    """Thin wrapper around InferenceClient for a self-hosted TEI service."""

    def __init__(self, url: str, timeout: float = 120.0):
        self._url = url.rstrip("/")
        self._timeout = timeout

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    async def aembed_query(self, text: str) -> list[float]:
        result = await self._aembed([text])
        return result[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._aembed(texts)

    # ---- internal helpers ------------------------------------------------

    def _embed(self, texts: list[str]) -> list[list[float]]:
        # TEI root endpoint accepts {"inputs": [...]} and returns embeddings
        with httpx.Client(timeout=self._timeout, trust_env=False) as http:
            resp = http.post(
                f"{self._url}/",
                json={"inputs": texts},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def _aembed(self, texts: list[str], max_retries: int = 3) -> list[list[float]]:
        import asyncio
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as http:
                    resp = await http.post(
                        f"{self._url}/",
                        json={"inputs": texts},
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 502 and attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise


class EmbeddingClientManager(BaseClientManager):
    def __init__(self, config):
        super().__init__(config)
        self.client: LocalTEIEmbeddings | None = None

    def init(self):
        url = self._url()
        self.client = LocalTEIEmbeddings(url)
        logger.info(f"Embedding client initialized: {url}")

    async def close(self):
        pass


embedding_client_manager = EmbeddingClientManager(app_config.embedding)
