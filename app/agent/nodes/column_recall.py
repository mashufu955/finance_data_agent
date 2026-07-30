from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.nodes._recall_helpers import extend_keywords, vector_recall
from app.agent.state import DataAgentState
from app.core.logging import logger


async def column_recall(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """Recall column info from vector store."""
    writer = runtime.stream_writer
    writer({"stage": "召回字段信息"})

    keywords = state["keywords"]
    query = state["query"]
    column_qdrant_repository = runtime.context["column_qdrant_repository"]
    embedding_client = runtime.context["embedding_client"]

    try:
        keywords = await extend_keywords("extend_keywords_for_column_recall", query, keywords)
        retrieved_columns = await vector_recall(
            keywords,
            embed_fn=embedding_client.aembed_query,
            search_fn=lambda vec: column_qdrant_repository.search(vec, 0.6, 5),
        )
        logger.info(f"字段信息召回成功: {[c['id'] for c in retrieved_columns]}")
        return {"retrieved_columns": retrieved_columns}
    except Exception as e:
        logger.error(f"字段信息召回失败: {str(e)}")
        raise
