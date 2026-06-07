"""DocumentSearchAgent — turn a claim into search candidates.

Asks the LLM to:
  1. Rephrase the claim into 1-3 targeted search queries.
  2. Pick which engines to use (google / bing / wikipedia), respecting the
     `prefer_source` hint and what credentials are configured.

Then dispatches each query × engine in Python (deterministic, easy to retry).
"""

from __future__ import annotations

import logging
from asyncio import gather

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.domain.state import FactCheckState, SearchOutput
from app.platform.config import get_settings
from app.platform.llm import get_llm
from app.tools import SEARCH_SOURCES
from app.tools.sources import SearchHit, SearchSource

log = logging.getLogger(__name__)

SYSTEM = """You are the search-planning step of a fact-checking pipeline.

Given a claim and a hint about preferred sources, decide:
  - 1 to 3 short search queries that would surface evidence for or against the claim
  - which engines to run them on, from the available engines list
"""


class SearchPlan(BaseModel):
    queries: list[str]
    engines: list[str]


def _available_engines() -> list[SearchSource]:
    settings = get_settings()
    out: list[SearchSource] = ["wikipedia"]
    if settings.google_api_key and settings.google_cse_id:
        out.append("google")
    if settings.bing_api_key:
        out.append("bing")
    return out


async def _plan(
    claim: str, prefer_source: str, tried: list[str]
) -> tuple[list[str], list[SearchSource]]:
    available_engines = _available_engines()
    user = (
        f"Claim: {claim}\n"
        f"prefer_source: {prefer_source}\n"
        f"Available engines: {available_engines}\n"
    )
    if tried:
        user += (
            f"\nThese queries were ALREADY tried and returned no usable results: {tried}\n"
            "Generate DIFFERENT queries this time — rephrase, broaden or narrow the scope, "
            "use synonyms, key entities, or alternate spellings. Do NOT repeat any tried query.\n"
        )
    user += "Pick engines only from the available list."
    try:
        result = await (
            get_llm()
            .with_structured_output(SearchPlan, method="json_schema")
            .ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=user)])
        )
        if not isinstance(result, SearchPlan):
            raise TypeError(f"Unexpected structured output type: {type(result)}")
        queries = [q for q in result.queries if isinstance(q, str)][:3]
        engines = [e for e in available_engines if e in result.engines]
    except Exception:
        log.warning("Search planner structured output failed; falling back to defaults")
        queries, engines = [claim], available_engines

    if not queries:
        queries = [claim]
    if not engines:
        engines = available_engines
    return queries, engines


def _dispatch(queries: list[str], engines: list[SearchSource]) -> list[SearchHit]:
    count = get_settings().search_results_per_query
    seen: set[str] = set()
    hits: list[SearchHit] = []
    for query in queries:
        for engine in engines:
            tool = SEARCH_SOURCES[engine]
            try:
                result = tool.invoke({"query": query, "count": count})
            except Exception as e:
                log.warning("Search tool %s failed for %r: %s", engine, query, e)
                continue
            log.info("Search tool %s returned %d hits for %r", engine, len(result), query)
            for hit in result:
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)
    return hits


async def document_search_agent(state: FactCheckState) -> SearchOutput:
    queries, engines = await _plan(state.claim, state.prefer_source, state.search_queries)
    log.info(
        "Search plan (attempt %d): queries=%s engines=%s already_tried=%s",
        state.retries + 1,
        queries,
        engines,
        state.search_queries,
    )
    candidates = _dispatch(queries, engines)
    return SearchOutput(search_queries=queries, candidates=candidates)
