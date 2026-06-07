"""DuckDuckGo search wrapped as an async LangChain tool.

`ddgs` is a synchronous library, so the blocking call runs in a worker thread
via ``asyncio.to_thread`` to keep the event loop free.
"""

from __future__ import annotations

import asyncio

from ddgs import DDGS
from ddgs.exceptions import DDGSException
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.tools.sources import SearchHit


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(DDGSException),
)
def _search_sync(query: str, count: int) -> list[SearchHit]:
    results = DDGS().text(query, max_results=count)
    return [
        SearchHit(
            url=r["href"],
            title=r.get("title", ""),
            snippet=r.get("body", ""),
            source="duckduckgo",
        )
        for r in results
        if r.get("href")
    ]


@tool
async def duckduckgo_search(query: str, count: int = 3) -> list[SearchHit]:
    """Search DuckDuckGo for the given query and return up to `count` web results.

    Best for: general web evidence, news, blog posts, current events. No API key required.
    Returns: list of {url, title, snippet, source}.
    """
    return await asyncio.to_thread(_search_sync, query, min(max(count, 1), 10))
