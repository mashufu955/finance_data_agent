from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.clients.base import BaseClientManager
from app.config.app_config import DBConfig, app_config


class MySQLClientManager(BaseClientManager):
    def __init__(self, db_config: DBConfig):
        super().__init__(db_config)
        self.engine = None
        self.session_factory = None

    def _db_url(self):
        c = self.config
        return f"mysql+asyncmy://{c.user}:{c.password}@{c.host}:{c.port}/{c.database}?charset=utf8mb4"

    def init(self):
        self.engine = create_async_engine(
            self._db_url(),
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False
        )

    async def close(self):
        await self.engine.dispose()


# 实例化全局对象
dw_client_manager = MySQLClientManager(app_config.db_dw)
meta_client_manager = MySQLClientManager(app_config.db_meta)
