"""Tests for agent node error branches, pure functions, and converters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_agent.test_nodes import _make_state, _stop


# ===========================================================================
# 1. Error-handling branches (except Exception -> log + raise)
# ===========================================================================

class TestNodeErrorBranches:
    """Each node wraps its logic in try/except; verify errors propagate."""

    @pytest.mark.asyncio
    async def test_column_recall_error(self, mock_runtime):
        from app.agent.nodes.column_recall import column_recall
        state = _make_state()
        with patch("app.agent.nodes.column_recall.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.column_recall.PromptTemplate", side_effect=RuntimeError("recall fail")):
                with pytest.raises(RuntimeError, match="recall fail"):
                    await column_recall(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_correct_sql_error(self, mock_runtime):
        from app.agent.nodes.correct_sql import correct_sql
        state = _make_state(sql="SELECT * FROM t", error="syntax error")
        with patch("app.agent.nodes.correct_sql.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.correct_sql.PromptTemplate", side_effect=RuntimeError("correct fail")):
                with pytest.raises(RuntimeError, match="correct fail"):
                    await correct_sql(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_execute_sql_error(self, mock_runtime):
        from app.agent.nodes.execute_sql import execute_sql
        state = _make_state(sql="SELECT bad")
        mock_runtime.context["dw_mysql_repository"].execute_sql = AsyncMock(
            side_effect=RuntimeError("exec fail")
        )
        with pytest.raises(RuntimeError, match="exec fail"):
            await execute_sql(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_filter_metric_info_error(self, mock_runtime):
        from app.agent.nodes.filter_metric_info import filter_metric_info
        state = _make_state(metric_infos=[{"name": "m1", "description": "d", "alias": []}])
        with patch("app.agent.nodes.filter_metric_info.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.filter_metric_info.PromptTemplate", side_effect=RuntimeError("filter fail")):
                with pytest.raises(RuntimeError, match="filter fail"):
                    await filter_metric_info(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_filter_table_info_error(self, mock_runtime):
        from app.agent.nodes.filter_table_info import filter_table_info
        state = _make_state(table_infos=[{
            "name": "t1", "role": "fact", "description": "d",
            "columns": [{"name": "c1", "type": "int", "role": "dimension",
                         "description": "d", "alias": [], "examples": []}]
        }])
        with patch("app.agent.nodes.filter_table_info.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.filter_table_info.PromptTemplate", side_effect=RuntimeError("filter fail")):
                with pytest.raises(RuntimeError, match="filter fail"):
                    await filter_table_info(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_generate_sql_error(self, mock_runtime):
        from app.agent.nodes.generate_sql import generate_sql
        state = _make_state()
        with patch("app.agent.nodes.generate_sql.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.generate_sql.PromptTemplate", side_effect=RuntimeError("gen fail")):
                with pytest.raises(RuntimeError, match="gen fail"):
                    await generate_sql(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_metric_recall_error(self, mock_runtime):
        from app.agent.nodes.metric_recall import metric_recall
        state = _make_state()
        with patch("app.agent.nodes.metric_recall.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.metric_recall.PromptTemplate", side_effect=RuntimeError("metric fail")):
                with pytest.raises(RuntimeError, match="metric fail"):
                    await metric_recall(state, mock_runtime)

    @pytest.mark.asyncio
    async def test_value_recall_error(self, mock_runtime):
        from app.agent.nodes.value_recall import value_recall
        state = _make_state()
        with patch("app.agent.nodes.value_recall.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.value_recall.PromptTemplate", side_effect=RuntimeError("value fail")):
                with pytest.raises(RuntimeError, match="value fail"):
                    await value_recall(state, mock_runtime)


# ===========================================================================
# 2. Pure functions from extract_keywords
# ===========================================================================

class TestExtractKeywordsHelpers:
    def test_is_numeric_int(self):
        from app.agent.nodes.extract_keywords import is_numeric
        assert is_numeric("123") is True

    def test_is_numeric_float(self):
        from app.agent.nodes.extract_keywords import is_numeric
        assert is_numeric("3.14") is True

    def test_is_numeric_negative(self):
        from app.agent.nodes.extract_keywords import is_numeric
        assert is_numeric("-42") is True

    def test_is_numeric_string(self):
        from app.agent.nodes.extract_keywords import is_numeric
        assert is_numeric("hello") is False

    def test_is_numeric_empty(self):
        from app.agent.nodes.extract_keywords import is_numeric
        assert is_numeric("") is False

    def test_is_numeric_none(self):
        from app.agent.nodes.extract_keywords import is_numeric
        assert is_numeric(None) is False

    def test_apply_synonyms_basic(self):
        from app.agent.nodes.extract_keywords import _apply_synonyms
        assert "客户数" in _apply_synonyms("用户数是多少")

    def test_apply_synonyms_aum(self):
        from app.agent.nodes.extract_keywords import _apply_synonyms
        result = _apply_synonyms("AUM有多少")
        assert "理财持仓规模" in result

    def test_apply_synonyms_no_match(self):
        from app.agent.nodes.extract_keywords import _apply_synonyms
        result = _apply_synonyms("今天天气怎么样")
        assert result == "今天天气怎么样"

    def test_apply_synonyms_longer_phrase_priority(self):
        from app.agent.nodes.extract_keywords import _apply_synonyms
        # "新增用户数" should match as a whole, not "新增用户" + "数"
        result = _apply_synonyms("新增用户数有多少")
        assert "新增客户数" in result


# ===========================================================================
# 3. Converter functions from merge_retrieved_info
# ===========================================================================

class TestMergeConverters:
    def test_convert_mysql_to_qdrant(self, sample_column_mysql):
        from app.agent.nodes.merge_retrieved_info import _convert_column_info_from_mysql_to_qdrant
        result = _convert_column_info_from_mysql_to_qdrant(sample_column_mysql)
        assert result["id"] == "dw_customer.risk_level"
        assert result["name"] == "risk_level"
        assert result["table_id"] == "dw_customer"

    def test_convert_qdrant_to_state(self, sample_column_qdrant):
        from app.agent.nodes.merge_retrieved_info import _convert_column_info_from_qdrant_to_state
        result = _convert_column_info_from_qdrant_to_state(sample_column_qdrant)
        assert result["name"] == "customer_name"
        assert result["type"] == "varchar(128)"
        assert result["role"] == "dimension"

    def test_convert_mysql_to_state(self, sample_column_mysql):
        from app.agent.nodes.merge_retrieved_info import _convert_column_info_from_mysql_to_state
        result = _convert_column_info_from_mysql_to_state(sample_column_mysql)
        assert result["name"] == "risk_level"
        assert result["type"] == "varchar(32)"


# ===========================================================================
# 4. filter_table_info column pruning branch
# ===========================================================================

class TestFilterTableInfoColumnPruning:
    @pytest.mark.asyncio
    async def test_column_pruning_partial(self, mock_runtime):
        """LLM keeps the table but drops some columns."""
        from app.agent.nodes.filter_table_info import filter_table_info

        state = _make_state(table_infos=[{
            "name": "t1", "role": "fact", "description": "d",
            "columns": [
                {"name": "keep_col", "type": "int", "role": "dimension",
                 "description": "d", "alias": [], "examples": []},
                {"name": "drop_col", "type": "varchar", "role": "dimension",
                 "description": "d", "alias": [], "examples": []},
            ]
        }])

        chain_mock = MagicMock()
        chain_mock.ainvoke = AsyncMock(return_value={"t1": ["keep_col"]})

        with patch("app.agent.nodes.filter_table_info.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.filter_table_info.PromptTemplate") as mock_pt:
                mock_pt.return_value.__or__ = MagicMock(
                    return_value=MagicMock(__or__=MagicMock(return_value=chain_mock))
                )
                result = await filter_table_info(state, mock_runtime)

        tables = result["table_infos"]
        assert len(tables) == 1
        assert len(tables[0]["columns"]) == 1
        assert tables[0]["columns"][0]["name"] == "keep_col"

    @pytest.mark.asyncio
    async def test_table_removed_entirely(self, mock_runtime):
        """LLM drops a table entirely."""
        from app.agent.nodes.filter_table_info import filter_table_info

        state = _make_state(table_infos=[{
            "name": "t1", "role": "fact", "description": "d",
            "columns": [
                {"name": "c1", "type": "int", "role": "dimension",
                 "description": "d", "alias": [], "examples": []},
            ]
        }])

        chain_mock = MagicMock()
        chain_mock.ainvoke = AsyncMock(return_value={})

        with patch("app.agent.nodes.filter_table_info.load_prompt", return_value="dummy"):
            with patch("app.agent.nodes.filter_table_info.PromptTemplate") as mock_pt:
                mock_pt.return_value.__or__ = MagicMock(
                    return_value=MagicMock(__or__=MagicMock(return_value=chain_mock))
                )
                result = await filter_table_info(state, mock_runtime)

        assert len(result["table_infos"]) == 0


# ===========================================================================
# 5. merge_retrieved_info edge cases
# ===========================================================================

class TestMergeRetrievedInfoEdgeCases:
    @pytest.mark.asyncio
    async def test_value_recall_finds_new_column(self, mock_runtime, sample_column_mysql):
        """Value recall finds a column not in column recall results."""
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        mock_runtime.context["meta_mysql_repository"].get_column_by_id = AsyncMock(
            return_value=sample_column_mysql
        )
        mock_runtime.context["meta_mysql_repository"].get_table_by_id = AsyncMock(
            return_value=MagicMock(id="dw_customer", name="dw_customer",
                                   role="fact", description="desc")
        )
        mock_runtime.context["meta_mysql_repository"].get_key_columns_by_table_id = AsyncMock(
            return_value=[]
        )

        state = _make_state(
            retrieved_columns=[],
            retrieved_values=[{
                "id": "dw_customer.risk_level.R1", "value": "R1",
                "type": "varchar", "column_id": "dw_customer.risk_level",
                "column_name": "risk_level", "table_id": "dw_customer",
                "table_name": "dw_customer",
            }],
            retrieved_metrics=[],
        )
        result = await merge_retrieved_info(state, mock_runtime)
        assert len(result["table_infos"]) == 1
        cols = result["table_infos"][0]["columns"]
        assert any(c["name"] == "risk_level" for c in cols)

    @pytest.mark.asyncio
    async def test_key_columns_appended(self, mock_runtime, sample_column_mysql, sample_column_qdrant):
        """Key columns (PK/FK) from MySQL are appended if not already present."""
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        mock_runtime.context["meta_mysql_repository"].get_table_by_id = AsyncMock(
            return_value=MagicMock(id="dw_customer", name="dw_customer",
                                   role="fact", description="desc")
        )
        mock_runtime.context["meta_mysql_repository"].get_key_columns_by_table_id = AsyncMock(
            return_value=[sample_column_mysql]
        )

        state = _make_state(
            retrieved_columns=[sample_column_qdrant],
            retrieved_values=[],
            retrieved_metrics=[],
        )
        result = await merge_retrieved_info(state, mock_runtime)
        cols = result["table_infos"][0]["columns"]
        # sample_column_qdrant (customer_name) + sample_column_mysql (risk_level as key)
        col_names = [c["name"] for c in cols]
        assert "customer_name" in col_names
        assert "risk_level" in col_names
