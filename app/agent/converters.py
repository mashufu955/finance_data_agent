"""Type converters between MySQL ORM models, Qdrant payloads, and agent state."""

from __future__ import annotations

from app.agent.state import ColumnInfoState
from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.models.mysql.metric_info_mysql import MetricInfoMySQL
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant


def column_mysql_to_qdrant(column_info: ColumnInfoMySQL) -> ColumnInfoQdrant:
    return ColumnInfoQdrant(
        id=column_info.id,
        name=column_info.name,
        type=column_info.type,
        role=column_info.role,
        examples=column_info.examples,
        description=column_info.description,
        alias=column_info.alias,
        table_id=column_info.table_id,
    )


def column_qdrant_to_state(column_info: ColumnInfoQdrant) -> ColumnInfoState:
    return ColumnInfoState(
        name=column_info["name"],
        type=column_info["type"],
        role=column_info["role"],
        description=column_info["description"],
        alias=column_info["alias"],
        examples=column_info["examples"],
    )


def column_mysql_to_state(column_info: ColumnInfoMySQL) -> ColumnInfoState:
    return ColumnInfoState(
        name=column_info.name,
        type=column_info.type,
        role=column_info.role,
        description=column_info.description,
        alias=column_info.alias,
        examples=column_info.examples,
    )


def metric_mysql_to_qdrant(metric_info: MetricInfoMySQL) -> MetricInfoQdrant:
    return MetricInfoQdrant(
        id=metric_info.id,
        name=metric_info.name,
        description=metric_info.description,
        relevant_columns=metric_info.relevant_columns,
        alias=metric_info.alias,
    )
