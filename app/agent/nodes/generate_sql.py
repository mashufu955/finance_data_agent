from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.logging import logger
from app.prompt.prompt_loader import load_prompt


async def generate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    writer({"stage": "生成SQL"})

    table_infos = state["table_infos"]
    metric_infos = state["metric_infos"]
    date_info = state["date_info"]
    db_info = state["db_info"]
    query = state["query"]
    query_type = state.get("query_type", "simple_metric")
    time_range = state.get("time_range")

    try:
        prompt = PromptTemplate(template=load_prompt("generate_sql"),
                                input_variables=["table_infos", "metric_infos", "date_info", "db_info",
                                                 "query", "query_type", "time_range"])
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {"table_infos": table_infos, "metric_infos": metric_infos, "date_info": date_info,
             "db_info": db_info, "query": query, "query_type": query_type,
             "time_range": time_range or "未指定"})

        logger.info(f"生成SQL: {result}")
        return {"sql": result}
    except Exception as e:
        logger.error(f"生成SQL失败: {e}")
        raise
