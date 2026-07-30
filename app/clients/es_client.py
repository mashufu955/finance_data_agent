from elasticsearch import AsyncElasticsearch

from app.clients.base import BaseClientManager
from app.config.app_config import ESConfig, app_config


class ESClientManager(BaseClientManager):
    def __init__(self, config: ESConfig):
        super().__init__(config)
        self.client: AsyncElasticsearch | None = None

    def init(self):
        self.client = AsyncElasticsearch(hosts=[self._url()])

    async def close(self):
        await self.client.close()


es_client_manager = ESClientManager(app_config.es)
