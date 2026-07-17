"""Integration test for the full agent pipeline graph with all nodes mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fully_mocked_graph():
    """
    Build the graph with every node replaced by a mock that returns
    deterministic state updates, so we can test the wiring without
    needing LLM / Qdrant / ES / MySQL.
    """
    from langgraph.constants import END, START
    from langgraph.graph import StateGraph

    from app.agent.state import DataAgentState

    # --- mock nodes ---
    async def mock_classify(state, runtime):
        return {"query_type": "simple_metric", "business_domains": ["customer"], "time_range": "本月"}

    async def mock_extract(state, runtime):
        return {"keywords": ["新增客户数", "本月"]}

    async def mock_column_recall(state, runtime):
        return {"retrieved_columns": []}

    async def mock_value_recall(state, runtime):
        return {"retrieved_values": []}

    async def mock_metric_recall(state, runtime):
        return {"retrieved_metrics": []}

    async def mock_merge(state, runtime):
        return {"table_infos": [], "metric_infos": []}

    async def mock_filter_table(state, runtime):
        return {"table_infos": []}

    async def mock_filter_metric(state, runtime):
        return {"metric_infos": []}

    async def mock_add_context(state, runtime):
        return {
            "date_info": {"date": "2026-07-16", "weekday": "Thursday", "quarter": "Q3"},
            "db_info": {"dialect": "mysql", "version": "8.0.0"},
        }

    async def mock_generate_sql(state, runtime):
        return {"sql": "SELECT COUNT(*) AS cnt FROM dw_customer"}

    async def mock_validate_sql(state, runtime):
        return {"error": None}

    async def mock_execute_sql(state, runtime):
        return {"query_result": [{"cnt": 42}]}

    async def mock_format_result(state, runtime):
        return {"result_summary": "本月新增客户数为 42 户。"}

    # Build a separate graph with mock nodes
    builder = StateGraph(state_schema=DataAgentState)
    builder.add_node("classify_query", mock_classify)
    builder.add_node("extract_keywords", mock_extract)
    builder.add_node("column_recall", mock_column_recall)
    builder.add_node("value_recall", mock_value_recall)
    builder.add_node("metric_recall", mock_metric_recall)
    builder.add_node("merge_retrieved_info", mock_merge)
    builder.add_node("filter_table_info", mock_filter_table)
    builder.add_node("filter_metric_info", mock_filter_metric)
    builder.add_node("add_context", mock_add_context)
    builder.add_node("generate_sql", mock_generate_sql)
    builder.add_node("validate_sql", mock_validate_sql)
    builder.add_node("execute_sql", mock_execute_sql)
    builder.add_node("format_result", mock_format_result)

    builder.add_edge(START, "classify_query")
    builder.add_edge("classify_query", "extract_keywords")
    builder.add_edge("extract_keywords", "column_recall")
    builder.add_edge("extract_keywords", "value_recall")
    builder.add_edge("extract_keywords", "metric_recall")
    builder.add_edge("column_recall", "merge_retrieved_info")
    builder.add_edge("value_recall", "merge_retrieved_info")
    builder.add_edge("metric_recall", "merge_retrieved_info")
    builder.add_edge("merge_retrieved_info", "filter_table_info")
    builder.add_edge("merge_retrieved_info", "filter_metric_info")
    builder.add_edge("filter_table_info", "add_context")
    builder.add_edge("filter_metric_info", "add_context")
    builder.add_edge("add_context", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    builder.add_conditional_edges(
        "validate_sql",
        lambda state: "execute_sql" if state.get("error") is None else "correct_sql",
    )
    builder.add_edge("execute_sql", "format_result")
    builder.add_edge("format_result", END)

    return builder.compile()


class TestGraphIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline_happy_path(self, fully_mocked_graph):
        """Run the full pipeline with mocked nodes and verify final state."""
        initial_state = {
            "query": "本月新增客户数是多少",
        }

        final = await fully_mocked_graph.ainvoke(initial_state)

        assert final["query_type"] == "simple_metric"
        assert final["business_domains"] == ["customer"]
        assert final["time_range"] == "本月"
        assert "新增客户数" in final["keywords"]
        assert final["sql"] == "SELECT COUNT(*) AS cnt FROM dw_customer"
        assert final["error"] is None
        assert final["query_result"] == [{"cnt": 42}]
        assert "42" in final["result_summary"]

    @pytest.mark.asyncio
    async def test_graph_node_count(self):
        """Verify the real graph has all 14 nodes registered."""
        from app.agent.graph import graph

        node_names = set(graph.get_graph().nodes.keys())
        expected = {
            "classify_query", "extract_keywords",
            "column_recall", "value_recall", "metric_recall",
            "merge_retrieved_info",
            "filter_table_info", "filter_metric_info",
            "add_context", "generate_sql", "validate_sql",
            "correct_sql", "execute_sql", "format_result",
        }
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"

    @pytest.mark.asyncio
    async def test_graph_edge_connectivity(self):
        """Verify key edges exist in the real graph."""
        from app.agent.graph import graph

        edges = graph.get_graph().edges
        # Check that START → classify_query exists
        assert any(e[0] == "classify_query" for e in edges)
        # Check that format_result → END exists
        assert any(e[0] == "format_result" for e in edges)
