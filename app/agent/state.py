from typing import Any, TypedDict

from app.models.es.value_info_es import ValueInfoES
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant


class MetricInfoState(TypedDict):
    name: str  # 指标名称
    description: str  # 指标描述
    alias: list[str]  # 指标别名


class ColumnInfoState(TypedDict):
    name: str  # 字段名称
    type: str  # 字段类型
    role: str  # 字段角色（primary_key/foreign_key/dimension/measure）
    description: str  # 字段描述
    alias: list[str]  # 字段别名
    examples: list[Any]  # 字段示例


class TableInfoState(TypedDict):
    name: str  # 表名称
    role: str  # 表角色（fact/dim）
    description: str  # 表描述
    columns: list[ColumnInfoState]  # 字段信息


class DateInfoState(TypedDict):
    date: str  # 日期
    weekday: str  # 星期
    quarter: str  # 季度


class DBInfoState(TypedDict):
    dialect: str  # 数据库方言
    version: str  # 数据库版本


class DataAgentState(TypedDict):
    query: str  # 查询

    # ---- 查询分类（由 classify_query 节点填充） ----
    query_type: str  # 查询类型: simple_metric / multi_dimension / trend / ranking / comparison / complex
    business_domains: list[str]  # 业务领域: customer / account / transaction / wealth / loan / repayment / risk / collection
    time_range: str  # 时间范围描述，如"本月""最近30天""2025年1月"，无则为空字符串

    keywords: list[str]  # 关键词列表，由query分词和LLM生成得到，用于召回信息
    retrieved_metrics: list[MetricInfoQdrant]  # 召回的指标信息
    retrieved_columns: list[ColumnInfoQdrant]  # 召回的字段信息
    retrieved_values: list[ValueInfoES]  # 召回的字段值信息

    table_infos: list[TableInfoState]  # 合并的表信息
    metric_infos: list[MetricInfoState]  # 召回的指标信息

    date_info: DateInfoState  # 当前的日期信息
    db_info: DBInfoState  # 数据库信息

    sql: str  # 生成的SQL语句
    error: str  # 校验SQL语句的错误信息

    query_result: list[dict]  # SQL执行结果（原始数据行）
    result_summary: str  # 自然语言结果说明（由 format_result 生成）
