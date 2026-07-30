"""Shared helpers for recall nodes (column / metric / value)."""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.agent.llm import llm
from app.core.logging import logger
from app.prompt.prompt_loader import load_prompt


async def extend_keywords(prompt_name: str, query: str, base_keywords: list[str]) -> list[str]:
    """Use LLM to extend the keyword list for better recall coverage."""
    prompt = PromptTemplate(template=load_prompt(prompt_name), input_variables=["query"])
    chain = prompt | llm | JsonOutputParser()
    extended = await chain.ainvoke({"query": query})
    return list(set(base_keywords + extended))


async def vector_recall(
    keywords: list[str],
    embed_fn: Callable[[str], Awaitable[list[float]]],
    search_fn: Callable[[list[float]], Awaitable[list[dict]]],
) -> list[dict]:
    """Generic vector recall: embed each keyword, search, deduplicate by id."""
    results_map: dict[str, dict] = {}
    for keyword in keywords:
        embedding = await embed_fn(keyword)
        hits = await search_fn(embedding)
        for hit in hits:
            if hit["id"] not in results_map:
                results_map[hit["id"]] = hit
    return list(results_map.values())


async def text_recall(
    keywords: list[str],
    query_fn: Callable[[str], Awaitable[list[dict]]],
) -> list[dict]:
    """Generic text/full-text recall: query each keyword, deduplicate by id."""
    results_map: dict[str, dict] = {}
    for keyword in keywords:
        hits = await query_fn(keyword)
        for hit in hits:
            if hit["id"] not in results_map:
                results_map[hit["id"]] = hit
    return list(results_map.values())
