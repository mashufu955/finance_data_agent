"""Base class for async client managers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseClientManager(ABC):
    """Common lifecycle pattern: init() creates client, close() disposes it."""

    def __init__(self, config):
        self.config = config
        self.client = None

    @abstractmethod
    def init(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    def _url(self, scheme: str = "http") -> str:
        return f"{scheme}://{self.config.host}:{self.config.port}"
