"""Column vector repository backed by Qdrant."""

from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.repositories.qdrant.base_repository_qdrant import BaseQdrantRepository


class ColumnQdrantRepository(BaseQdrantRepository[ColumnInfoQdrant]):
    collection_name = "data_agent_column"
