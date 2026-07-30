from qdrant_client import AsyncQdrantClient

from app.clients.base import BaseClientManager
from app.config.app_config import QdrantConfig, app_config


class QdrantClientManager(BaseClientManager):
    def __init__(self, config: QdrantConfig):
        super().__init__(config)
        self.client: AsyncQdrantClient | None = None

    def init(self):
        self.client = AsyncQdrantClient(
            url=self._url(),
            trust_env=False,
            check_compatibility=False,
        )

    async def close(self):
        await self.client.close()


qdrant_client_manager = QdrantClientManager(app_config.qdrant)
