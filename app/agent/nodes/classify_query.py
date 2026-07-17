from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.logging import logger
from app.prompt.prompt_loader import load_prompt


async def classify_query(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """对用户查询进行分类，识别查询类型、业务领域和时间范围，为下游节点提供路由依据。"""
    writer = runtime.stream_writer
    writer({"stage": "查询分类"})

    query = state["query"]

    try:
        prompt = PromptTemplate(
            template=load_prompt("classify_query"),
            input_variables=["query"],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke({"query": query})

        query_type = result.get("query_type", "simple_metric")
        business_domains = result.get("business_domains", [])
        time_range = result.get("time_range")

        logger.info(
            f"查询分类结果: type={query_type}, domains={business_domains}, time_range={time_range}"
        )

        return {
            "query_type": query_type,
            "business_domains": business_domains,
            "time_range": time_range,
        }
    except Exception as e:
        logger.error(f"查询分类失败: {e}")
        # 降级：不阻塞主流程，使用默认值
        return {
            "query_type": "simple_metric",
            "business_domains": [],
            "time_range": None,
        }
