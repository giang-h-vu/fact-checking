"""DocumentSearchAgent — turn a claim into search candidates.

Asks the LLM to:
  1. Rephrase the claim into 1-3 targeted search queries.
  2. Pick which engines to use (duckduckgo / brave / wikipedia), respecting the
     `prefer_source` hint and what credentials are configured.

Each query is routed to ONE engine (no query × engine cartesian product); the
planned (query, engine) pairs are dispatched concurrently in Python.
"""

from __future__ import annotations

import logging
from asyncio import gather

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.domain.state import FactCheckState, SearchOutput
from app.platform.config import get_settings
from app.platform.llm import get_llm
from app.tools import SEARCH_SOURCES
from app.tools.sources import SearchHit, SearchSource

log = logging.getLogger(__name__)

# Hard cap on searches per attempt — bounds cost, latency, and rate-limit pressure
# even if the model ignores the "1 to 3" instruction and returns more.
MAX_SEARCHES = 3
# Web-search fallback: if a primary web engine fails retry the same query on this backup engine.
WEB_SEARCH_FALLBACK: dict[SearchSource, SearchSource] = {"brave": "duckduckgo"}

SYSTEM = """You are the search-planning step of a fact-checking pipeline.

Your task: rewrite the claim into 1 to 3 focused search queries, and assign each
query to exactly one engine. Never send the same query to more than one engine.

Engines:
  - wikipedia: encyclopedic, historical, or well-established facts.
  - brave: the web search engine — news, current events, recent or niche topics.

Apply the prefer_source hint:
  - auto: pick wikipedia or brave per query, whichever best fits the query.
  - wiki: assign every query to wikipedia.
  - web: assign every query to brave.

Only use engine names from the available engines list. If brave is not listed,
use the other web engine that is.
"""

class PlannedSearch(BaseModel):
    query: str
    engine: str


class SearchPlan(BaseModel):
    searches: list[PlannedSearch]


def _available_engines() -> list[SearchSource]:
    settings = get_settings()
    out: list[SearchSource] = ["wikipedia", "duckduckgo"]
    if settings.brave_api_key:
        out.append("brave")
    return out


def _resolve_engine(requested: str, available: list[SearchSource]) -> SearchSource | None:
    """Map a requested engine onto an available one.

    Returns it directly if available; otherwise substitutes its web fallback
    (e.g. brave -> duckduckgo when no Brave key is set); else None. This lets the
    planner always ask for "brave" for web search and have the code pick the real
    available engine.
    """
    for engine in available:
        if engine == requested:
            return engine
    for primary, backup in WEB_SEARCH_FALLBACK.items():
        if requested == primary and backup in available:
            return backup
    return None


async def _plan(
    claim: str, prefer_source: str, tried: list[str]
) -> list[tuple[str, SearchSource]]:
    """Return up to MAX_SEARCHES (query, engine) pairs — each query routed to one engine."""
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
    try:
        result = await (
            get_llm()
            .with_structured_output(SearchPlan, method="json_schema")
            .ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=user)])
        )
        if not isinstance(result, SearchPlan):
            raise TypeError(f"Unexpected structured output type: {type(result)}")
        resolved = (
            (p.query, _resolve_engine(p.engine, available_engines))
            for p in result.searches
            if isinstance(p.query, str) and p.query
        )
        plan: list[tuple[str, SearchSource]] = [
            (query, engine) for query, engine in resolved if engine is not None
        ][:MAX_SEARCHES]
    except Exception:
        log.warning("Search planner structured output failed; falling back to defaults")
        plan = []

    # Fallback: route the raw claim to every available engine (bounded by engine count).
    if not plan:
        plan = [(claim, engine) for engine in available_engines]
    return plan


def is_rate_limited(exc: Exception) -> bool:
    """True only for an HTTP 429 (rate limit / quota exceeded)."""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == httpx.codes.TOO_MANY_REQUESTS
    )


async def _run_one(engine: SearchSource, query: str, count: int) -> list[SearchHit]:
    tool = SEARCH_SOURCES[engine]
    try:
        result: list[SearchHit] = await tool.ainvoke({"query": query, "count": count})
        log.info("Search tool %s returned %d hits for %r", engine, len(result), query)
        return result
    except Exception as e:
        log.warning("Search tool %s failed for %r: %s", engine, query, e)
        fallback = WEB_SEARCH_FALLBACK.get(engine)
        if fallback is not None and is_rate_limited(e):
            log.info("%s rate-limited; falling back to %s for %r", engine, fallback, query)
            return await _run_one(fallback, query, count)
        return []


async def _dispatch(plan: list[tuple[str, SearchSource]]) -> list[SearchHit]:
    count = get_settings().search_results_per_query
    # One search per planned (query, engine) pair
    results = await gather(*(_run_one(engine, query, count) for query, engine in plan))

    seen: set[str] = set()
    hits: list[SearchHit] = []
    for result in results:
        for hit in result:
            if hit.url in seen:
                continue
            seen.add(hit.url)
            hits.append(hit)
    return hits


async def document_search_agent(state: FactCheckState) -> SearchOutput:
    plan = await _plan(state.claim, state.prefer_source, state.search_queries)
    # Dedup queries (preserve order) for the accumulating `search_queries` state.
    queries = list(dict.fromkeys(query for query, _ in plan))
    log.info(
        "Search plan (attempt %d): plan=%s already_tried=%s",
        state.retries + 1,
        plan,
        state.search_queries,
    )
    candidates = await _dispatch(plan)
    return SearchOutput(search_queries=queries, candidates=candidates)
