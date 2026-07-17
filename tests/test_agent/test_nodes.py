"""Unit tests for all 14 agent pipeline nodes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.state import (
    ColumnInfoState,
    DataAgentState,
    MetricInfoState,
    TableInfoState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides) -> DataAgentState:
    """Build a minimal DataAgentState with sensible defaults."""
    base: dict = {
        "query": "本月新增客户数是多少",
        "query_type": "simple_metric",
        "business_domains": ["customer"],
        "time_range": "本月",
        "keywords": ["本月", "新增客户数"],
        "retrieved_metrics": [],
        "retrieved_columns": [],
        "retrieved_values": [],
        "table_infos": [],
        "metric_infos": [],
        "date_info": {"date": "2026-07-16", "weekday": "Thursday", "quarter": "Q3"},
        "db_info": {"dialect": "mysql", "version": "8.0.0"},
        "sql": "",
        "error": None,
        "query_result": [],
        "result_summary": "",
    }
    base.update(overrides)
    return base


def _mock_llm_chain(module_path: str, return_value, *, is_async=True, is_json=False):
    """
    Patch PromptTemplate / OutputParser / llm in *module_path* so that the
    ``prompt | llm | parser`` chain resolves to a mock whose ainvoke/invoke
    returns *return_value*.

    Returns a list of patchers that must be stopped after the test.
    """
    chain_mock = MagicMock()
    if is_async:
        chain_mock.ainvoke = AsyncMock(return_value=return_value)
    else:
        chain_mock.invoke = MagicMock(return_value=return_value)

    prompt_cls = patch(f"{module_path}.PromptTemplate")
    if is_json:
        parser_cls = patch(f"{module_path}.JsonOutputParser")
    else:
        parser_cls = patch(f"{module_path}.StrOutputParser")

    p1 = prompt_cls.start()
    p3 = parser_cls.start()

    # prompt_template | llm → intermediate; intermediate | parser → chain_mock
    prompt_inst = p1.return_value
    intermediate = MagicMock()
    prompt_inst.__or__ = MagicMock(return_value=intermediate)
    intermediate.__or__ = MagicMock(return_value=chain_mock)

    return chain_mock, [p1, p3]


def _stop(patches: list):
    for p in patches:
        p.stop()


# ===========================================================================
# 1. extract_keywords
# ===========================================================================

class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_basic_extraction(self, mock_runtime):
        from app.agent.nodes.extract_keywords import extract_keywords

        state = _make_state()
        result = await extract_keywords(state, mock_runtime)
        keywords = result["keywords"]
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert "本月新增客户数是多少" in keywords

    @pytest.mark.asyncio
    async def test_synonym_replacement(self, mock_runtime):
        from app.agent.nodes.extract_keywords import extract_keywords

        state = _make_state(query="用户数有多少")
        result = await extract_keywords(state, mock_runtime)
        keywords = result["keywords"]
        assert any("客户数" in k for k in keywords)

    @pytest.mark.asyncio
    async def test_synonym_aum(self, mock_runtime):
        from app.agent.nodes.extract_keywords import extract_keywords

        state = _make_state(query="AUM是多少")
        result = await extract_keywords(state, mock_runtime)
        keywords = result["keywords"]
        assert any("理财持仓规模" in k for k in keywords)

    @pytest.mark.asyncio
    async def test_time_range_appended(self, mock_runtime):
        from app.agent.nodes.extract_keywords import extract_keywords

        state = _make_state(time_range="最近30天")
        result = await extract_keywords(state, mock_runtime)
        assert "最近30天" in result["keywords"]

    @pytest.mark.asyncio
    async def test_no_time_range(self, mock_runtime):
        from app.agent.nodes.extract_keywords import extract_keywords

        state = _make_state(time_range=None)
        result = await extract_keywords(state, mock_runtime)
        assert isinstance(result["keywords"], list)

    @pytest.mark.asyncio
    async def test_numeric_filtered(self, mock_runtime):
        from app.agent.nodes.extract_keywords import extract_keywords

        state = _make_state(query="2025年交易金额")
        result = await extract_keywords(state, mock_runtime)
        assert "2025" not in result["keywords"]


# ===========================================================================
# 2. classify_query
# ===========================================================================

class TestClassifyQuery:
    @pytest.mark.asyncio
    async def test_simple_metric(self, mock_runtime):
        from app.agent.nodes.classify_query import classify_query

        mock_result = {
            "query_type": "simple_metric",
            "business_domains": ["customer"],
            "time_range": "本月",
        }
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.classify_query", mock_result, is_json=True
        )
        try:
            with patch("app.agent.nodes.classify_query.load_prompt", return_value="mock"):
                state = _make_state()
                result = await classify_query(state, mock_runtime)
        finally:
            _stop(patches)

        assert result["query_type"] == "simple_metric"
        assert "customer" in result["business_domains"]
        assert result["time_range"] == "本月"

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, mock_runtime):
        from app.agent.nodes.classify_query import classify_query

        with patch("app.agent.nodes.classify_query.load_prompt", side_effect=FileNotFoundError("not found")):
            state = _make_state()
            result = await classify_query(state, mock_runtime)

        assert result["query_type"] == "simple_metric"
        assert result["business_domains"] == []
        assert result["time_range"] is None


# ===========================================================================
# 3. column_recall
# ===========================================================================

class TestColumnRecall:
    @pytest.mark.asyncio
    async def test_recall_with_results(self, mock_runtime, sample_column_qdrant):
        from app.agent.nodes.column_recall import column_recall

        mock_runtime.context["column_qdrant_repository"].search = AsyncMock(
            return_value=[sample_column_qdrant]
        )
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.column_recall", ["客户"], is_json=True
        )
        try:
            with patch("app.agent.nodes.column_recall.load_prompt", return_value="mock"):
                state = _make_state()
                result = await column_recall(state, mock_runtime)
        finally:
            _stop(patches)

        assert len(result["retrieved_columns"]) == 1
        assert result["retrieved_columns"][0]["name"] == "customer_name"

    @pytest.mark.asyncio
    async def test_recall_empty(self, mock_runtime):
        from app.agent.nodes.column_recall import column_recall

        mock_runtime.context["column_qdrant_repository"].search = AsyncMock(return_value=[])
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.column_recall", [], is_json=True
        )
        try:
            with patch("app.agent.nodes.column_recall.load_prompt", return_value="mock"):
                state = _make_state()
                result = await column_recall(state, mock_runtime)
        finally:
            _stop(patches)

        assert result["retrieved_columns"] == []


# ===========================================================================
# 4. value_recall
# ===========================================================================

class TestValueRecall:
    @pytest.mark.asyncio
    async def test_recall_with_results(self, mock_runtime, sample_value_es):
        from app.agent.nodes.value_recall import value_recall

        mock_runtime.context["value_es_repository"].query = AsyncMock(
            return_value=[sample_value_es]
        )
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.value_recall", ["R1"], is_json=True
        )
        try:
            with patch("app.agent.nodes.value_recall.load_prompt", return_value="mock"):
                state = _make_state()
                result = await value_recall(state, mock_runtime)
        finally:
            _stop(patches)

        assert len(list(result["retrieved_values"])) == 1
        assert list(result["retrieved_values"])[0]["value"] == "R1"

    @pytest.mark.asyncio
    async def test_recall_empty(self, mock_runtime):
        from app.agent.nodes.value_recall import value_recall

        mock_runtime.context["value_es_repository"].query = AsyncMock(return_value=[])
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.value_recall", [], is_json=True
        )
        try:
            with patch("app.agent.nodes.value_recall.load_prompt", return_value="mock"):
                state = _make_state()
                result = await value_recall(state, mock_runtime)
        finally:
            _stop(patches)

        assert list(result["retrieved_values"]) == []


# ===========================================================================
# 5. metric_recall
# ===========================================================================

class TestMetricRecall:
    @pytest.mark.asyncio
    async def test_recall_with_results(self, mock_runtime, sample_metric_qdrant):
        from app.agent.nodes.metric_recall import metric_recall

        mock_runtime.context["metric_qdrant_repository"].search = AsyncMock(
            return_value=[sample_metric_qdrant]
        )
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.metric_recall", ["新增客户"], is_async=False, is_json=True
        )
        try:
            with patch("app.agent.nodes.metric_recall.load_prompt", return_value="mock"):
                state = _make_state()
                result = await metric_recall(state, mock_runtime)
        finally:
            _stop(patches)

        assert len(list(result["retrieved_metrics"])) == 1
        assert list(result["retrieved_metrics"])[0]["name"] == "新增客户数"


# ===========================================================================
# 6. merge_retrieved_info
# ===========================================================================

class TestMergeRetrievedInfo:
    @pytest.mark.asyncio
    async def test_merge_columns_into_tables(self, mock_runtime, sample_column_qdrant,
                                              sample_table_mysql, sample_column_mysql):
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        mock_runtime.context["meta_mysql_repository"].get_table_by_id = AsyncMock(
            return_value=sample_table_mysql
        )
        mock_runtime.context["meta_mysql_repository"].get_column_by_id = AsyncMock(
            return_value=sample_column_mysql
        )
        mock_runtime.context["meta_mysql_repository"].get_key_columns_by_table_id = AsyncMock(
            return_value=[]
        )

        state = _make_state(
            retrieved_columns=[sample_column_qdrant],
            retrieved_values=[],
            retrieved_metrics=[],
        )
        result = await merge_retrieved_info(state, mock_runtime)

        assert len(result["table_infos"]) == 1
        assert result["table_infos"][0]["name"] == "dw_customer"
        assert any(c["name"] == "customer_name" for c in result["table_infos"][0]["columns"])

    @pytest.mark.asyncio
    async def test_merge_with_metrics(self, mock_runtime, sample_metric_qdrant,
                                       sample_column_mysql, sample_table_mysql):
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        mock_runtime.context["meta_mysql_repository"].get_column_by_id = AsyncMock(
            return_value=sample_column_mysql
        )
        mock_runtime.context["meta_mysql_repository"].get_table_by_id = AsyncMock(
            return_value=sample_table_mysql
        )
        mock_runtime.context["meta_mysql_repository"].get_key_columns_by_table_id = AsyncMock(
            return_value=[]
        )

        state = _make_state(
            retrieved_columns=[],
            retrieved_values=[],
            retrieved_metrics=[sample_metric_qdrant],
        )
        result = await merge_retrieved_info(state, mock_runtime)

        assert len(result["metric_infos"]) == 1
        assert result["metric_infos"][0]["name"] == "新增客户数"
        assert len(result["table_infos"]) >= 1

    @pytest.mark.asyncio
    async def test_merge_values_add_examples(self, mock_runtime, sample_value_es, sample_table_mysql):
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        column = {
            "id": "dw_customer.risk_level",
            "name": "risk_level",
            "type": "varchar",
            "role": "dimension",
            "examples": ["R2", "R3"],
            "description": "风险等级",
            "alias": ["风险级别"],
            "table_id": "dw_customer",
        }

        mock_runtime.context["meta_mysql_repository"].get_table_by_id = AsyncMock(
            return_value=sample_table_mysql
        )
        mock_runtime.context["meta_mysql_repository"].get_key_columns_by_table_id = AsyncMock(
            return_value=[]
        )

        state = _make_state(
            retrieved_columns=[column],
            retrieved_values=[sample_value_es],
            retrieved_metrics=[],
        )
        result = await merge_retrieved_info(state, mock_runtime)

        col = result["table_infos"][0]["columns"][0]
        assert "R1" in col["examples"]

    @pytest.mark.asyncio
    async def test_merge_empty(self, mock_runtime):
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        state = _make_state(retrieved_columns=[], retrieved_values=[], retrieved_metrics=[])
        result = await merge_retrieved_info(state, mock_runtime)
        assert result["table_infos"] == []
        assert result["metric_infos"] == []


# ===========================================================================
# 7. filter_table_info
# ===========================================================================

class TestFilterTableInfo:
    @pytest.mark.asyncio
    async def test_filter_keeps_relevant(self, mock_runtime):
        from app.agent.nodes.filter_table_info import filter_table_info

        table_infos = [
            TableInfoState(name="dw_customer", role="fact", description="客户表",
                           columns=[ColumnInfoState(name="id", type="int", role="primary_key",
                                                    description="ID", alias=[], examples=[])]),
            TableInfoState(name="dw_account", role="fact", description="账户表",
                           columns=[ColumnInfoState(name="id", type="int", role="primary_key",
                                                    description="ID", alias=[], examples=[])]),
        ]
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.filter_table_info", {"dw_customer": ["id"]}, is_json=True
        )
        try:
            with patch("app.agent.nodes.filter_table_info.load_prompt", return_value="mock"):
                state = _make_state(table_infos=table_infos)
                result = await filter_table_info(state, mock_runtime)
        finally:
            _stop(patches)

        assert len(result["table_infos"]) == 1
        assert result["table_infos"][0]["name"] == "dw_customer"


# ===========================================================================
# 8. filter_metric_info
# ===========================================================================

class TestFilterMetricInfo:
    @pytest.mark.asyncio
    async def test_filter_keeps_relevant(self, mock_runtime):
        from app.agent.nodes.filter_metric_info import filter_metric_info

        metric_infos = [
            MetricInfoState(name="新增客户数", description="新注册客户", alias=[]),
            MetricInfoState(name="交易金额", description="交易总额", alias=[]),
        ]
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.filter_metric_info", ["新增客户数"], is_json=True
        )
        try:
            with patch("app.agent.nodes.filter_metric_info.load_prompt", return_value="mock"):
                state = _make_state(metric_infos=metric_infos)
                result = await filter_metric_info(state, mock_runtime)
        finally:
            _stop(patches)

        assert len(result["metric_infos"]) == 1
        assert result["metric_infos"][0]["name"] == "新增客户数"


# ===========================================================================
# 9. add_context
# ===========================================================================

class TestAddContext:
    @pytest.mark.asyncio
    async def test_adds_date_and_db_info(self, mock_runtime):
        from app.agent.nodes.add_context import add_context

        state = _make_state()
        result = await add_context(state, mock_runtime)

        assert "date_info" in result
        assert "db_info" in result
        assert result["date_info"]["date"] is not None
        assert result["db_info"]["dialect"] == "mysql"


# ===========================================================================
# 10. generate_sql
# ===========================================================================

class TestGenerateSql:
    @pytest.mark.asyncio
    async def test_generates_sql(self, mock_runtime):
        from app.agent.nodes.generate_sql import generate_sql

        expected_sql = "SELECT COUNT(*) FROM dw_customer WHERE created_at >= '2026-07-01'"
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.generate_sql", expected_sql
        )
        try:
            with patch("app.agent.nodes.generate_sql.load_prompt", return_value="mock"):
                state = _make_state()
                result = await generate_sql(state, mock_runtime)
        finally:
            _stop(patches)

        assert result["sql"] == expected_sql

    @pytest.mark.asyncio
    async def test_passes_query_type(self, mock_runtime):
        from app.agent.nodes.generate_sql import generate_sql

        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.generate_sql", "SELECT 1"
        )
        try:
            with patch("app.agent.nodes.generate_sql.load_prompt", return_value="mock"):
                state = _make_state(query_type="trend", time_range="最近三个月")
                await generate_sql(state, mock_runtime)
                call_args = chain_mock.ainvoke.call_args[0][0]
                assert call_args["query_type"] == "trend"
                assert call_args["time_range"] == "最近三个月"
        finally:
            _stop(patches)


# ===========================================================================
# 11. validate_sql
# ===========================================================================

class TestValidateSql:
    @pytest.mark.asyncio
    async def test_valid_sql(self, mock_runtime):
        from app.agent.nodes.validate_sql import validate_sql

        mock_runtime.context["dw_mysql_repository"].validate_sql = AsyncMock(return_value=None)
        state = _make_state(sql="SELECT 1")
        result = await validate_sql(state, mock_runtime)
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_invalid_sql(self, mock_runtime):
        from app.agent.nodes.validate_sql import validate_sql

        mock_runtime.context["dw_mysql_repository"].validate_sql = AsyncMock(
            side_effect=Exception("Syntax error")
        )
        state = _make_state(sql="SELEC TYPO")
        result = await validate_sql(state, mock_runtime)
        assert "Syntax error" in result["error"]


# ===========================================================================
# 12. correct_sql
# ===========================================================================

class TestCorrectSql:
    @pytest.mark.asyncio
    async def test_corrects_sql(self, mock_runtime):
        from app.agent.nodes.correct_sql import correct_sql

        corrected = "SELECT COUNT(*) FROM dw_customer"
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.correct_sql", corrected
        )
        try:
            with patch("app.agent.nodes.correct_sql.load_prompt", return_value="mock"):
                state = _make_state(sql="SELEC TYPO", error="Syntax error")
                result = await correct_sql(state, mock_runtime)
        finally:
            _stop(patches)

        assert result["sql"] == corrected


# ===========================================================================
# 13. execute_sql
# ===========================================================================

class TestExecuteSql:
    @pytest.mark.asyncio
    async def test_executes_and_returns_result(self, mock_runtime):
        from app.agent.nodes.execute_sql import execute_sql

        expected = [{"cnt": 42}]
        mock_runtime.context["dw_mysql_repository"].execute_sql = AsyncMock(return_value=expected)

        state = _make_state(sql="SELECT COUNT(*) AS cnt FROM dw_customer")
        result = await execute_sql(state, mock_runtime)

        assert result["query_result"] == expected

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_runtime):
        from app.agent.nodes.execute_sql import execute_sql

        mock_runtime.context["dw_mysql_repository"].execute_sql = AsyncMock(return_value=[])
        state = _make_state(sql="SELECT 1 WHERE FALSE")
        result = await execute_sql(state, mock_runtime)
        assert result["query_result"] == []


# ===========================================================================
# 14. format_result
# ===========================================================================

class TestFormatResult:
    @pytest.mark.asyncio
    async def test_generates_summary(self, mock_runtime):
        from app.agent.nodes.format_result import format_result

        summary_text = "本月新增客户数为 42 户。"
        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.format_result", summary_text
        )
        try:
            with patch("app.agent.nodes.format_result.load_prompt", return_value="mock"):
                state = _make_state(
                    query_result=[{"cnt": 42}],
                    table_infos=[TableInfoState(name="dw_customer", role="fact",
                                                description="客户表", columns=[])],
                    metric_infos=[MetricInfoState(name="新增客户数", description="新客数", alias=[])],
                )
                result = await format_result(state, mock_runtime)
        finally:
            _stop(patches)

        assert result["result_summary"] == summary_text

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, mock_runtime):
        from app.agent.nodes.format_result import format_result

        with patch("app.agent.nodes.format_result.load_prompt", side_effect=FileNotFoundError()):
            state = _make_state(query_result=[{"cnt": 1}])
            result = await format_result(state, mock_runtime)

        assert "1" in result["result_summary"]

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_runtime):
        from app.agent.nodes.format_result import format_result

        chain_mock, patches = _mock_llm_chain(
            "app.agent.nodes.format_result", "未查询到符合条件的数据。"
        )
        try:
            with patch("app.agent.nodes.format_result.load_prompt", return_value="mock"):
                state = _make_state(query_result=[])
                result = await format_result(state, mock_runtime)
        finally:
            _stop(patches)

        assert "未查询到" in result["result_summary"]
