from qdrant_client import AsyncQdrantClient

from app.config.app_config import QdrantConfig, app_config


class QdrantClientManager:
    def __init__(self, config: QdrantConfig):
        self.config: QdrantConfig = config
        self.client: AsyncQdrantClient | None = None

    def _get_url(self):
        return f"http://{self.config.host}:{self.config.port}"

    def init(self):
        self.client = AsyncQdrantClient(
            url=f"http://{self.config.host}:{self.config.port}",
            trust_env=False,
            check_compatibility=False,
        )

    async def close(self):
        await self.client.close()


qdrant_client_manager = QdrantClientManager(app_config.qdrant)
