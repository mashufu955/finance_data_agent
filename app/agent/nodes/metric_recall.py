from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.nodes._recall_helpers import extend_keywords, vector_recall
from app.agent.state import DataAgentState
from app.core.logging import logger


async def metric_recall(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """Recall metric info from vector store."""
    writer = runtime.stream_writer
    writer({"stage": "召回指标信息"})

    keywords = state["keywords"]
    query = state["query"]
    embedding_client = runtime.context["embedding_client"]
    metric_qdrant_repository = runtime.context["metric_qdrant_repository"]

    try:
        keywords = await extend_keywords("extend_keywords_for_metric_recall", query, keywords)
        retrieved_metrics = await vector_recall(
            keywords,
            embed_fn=embedding_client.aembed_query,
            search_fn=lambda vec: metric_qdrant_repository.search(vec, score_threshold=0.6, limit=5),
        )
        logger.info(f"召回指标信息: {[m['id'] for m in retrieved_metrics]}")
        return {"retrieved_metrics": retrieved_metrics}
    except Exception as e:
        logger.error(f"召回指标信息失败: {str(e)}")
        raise
