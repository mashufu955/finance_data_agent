import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.logging import logger
from app.prompt.prompt_loader import load_prompt


async def format_result(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """将 SQL 执行结果转化为自然语言回答，包含口径说明和数据来源追溯。"""
    writer = runtime.stream_writer
    writer({"stage": "生成结果说明"})

    query = state["query"]
    sql = state.get("sql", "")
    table_infos = state.get("table_infos", [])
    metric_infos = state.get("metric_infos", [])
    query_result = state.get("query_result", [])
    query_type = state.get("query_type", "simple_metric")
    time_range = state.get("time_range")

    # 限制结果条数，避免 prompt 过长
    result_preview = query_result[:50] if query_result else []
    total_rows = len(query_result) if query_result else 0

    # 提取使用的表名列表
    tables_used = [t["name"] for t in table_infos] if table_infos else []
    metrics_used = [m["name"] for m in metric_infos] if metric_infos else []

    try:
        prompt = PromptTemplate(
            template=load_prompt("format_result"),
            input_variables=["query", "query_type", "time_range", "sql",
                             "tables_used", "metrics_used", "result_preview",
                             "total_rows"],
        )
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        summary = await chain.ainvoke({
            "query": query,
            "query_type": query_type,
            "time_range": time_range or "未指定",
            "sql": sql,
            "tables_used": ", ".join(tables_used) if tables_used else "未知",
            "metrics_used": ", ".join(metrics_used) if metrics_used else "无",
            "result_preview": json.dumps(result_preview, ensure_ascii=False, default=str),
            "total_rows": total_rows,
        })

        logger.info(f"结果说明生成完成")
        writer({"stage": "结果说明完成", "summary": summary})
        return {"result_summary": summary}
    except Exception as e:
        logger.error(f"结果说明生成失败: {e}")
        # 降级：返回简要摘要
        fallback = f"查询完成，共返回 {total_rows} 条结果。"
        return {"result_summary": fallback}
