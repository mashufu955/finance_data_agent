"""Metric vector repository backed by Qdrant."""

from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant
from app.repositories.qdrant.base_repository_qdrant import BaseQdrantRepository


class MetricQdrantRepository(BaseQdrantRepository[MetricInfoQdrant]):
    collection_name = "data_agent_metric"
