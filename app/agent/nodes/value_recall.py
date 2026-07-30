from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.nodes._recall_helpers import extend_keywords, text_recall
from app.agent.state import DataAgentState
from app.core.logging import logger


async def value_recall(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """Recall column values from Elasticsearch full-text index."""
    writer = runtime.stream_writer
    writer({"stage": "召回字段值"})

    keywords = state["keywords"]
    query = state["query"]
    value_es_repository = runtime.context["value_es_repository"]

    try:
        keywords = await extend_keywords("extend_keywords_for_value_recall", query, keywords)
        retrieved_values = await text_recall(
            keywords,
            query_fn=lambda kw: value_es_repository.query(kw, score_threshold=0.6, limit=5),
        )
        logger.info(f"召回字段值: {[v['id'] for v in retrieved_values]}")
        return {"retrieved_values": retrieved_values}
    except Exception as e:
        logger.error(f"召回字段值失败: {str(e)}")
        raise
