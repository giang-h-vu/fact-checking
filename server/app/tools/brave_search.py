"""Brave Web Search wrapped as an async LangChain tool."""

from __future__ import annotations

import httpx
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.platform.config import get_settings
from app.tools.sources import SearchHit

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _search(query: str, count: int) -> list[SearchHit]:
    settings = get_settings()
    if not settings.brave_api_key:
        raise RuntimeError("BRAVE_API_KEY must be set in .env")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            BRAVE_URL,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.brave_api_key,
            },
            params={"q": query, "count": count},
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        results = response.json().get("web", {}).get("results", [])
    return [
        SearchHit(
            url=r["url"],
            title=r.get("title", ""),
            snippet=r.get("description", ""),
            source="brave",
        )
        for r in results
        if r.get("url")
    ]


@tool
async def brave_search(query: str, count: int = 3) -> list[SearchHit]:
    """Search Brave for the given query and return up to `count` web results.

    Best for: general web evidence; an independent high-quality index that
    complements DuckDuckGo. Returns: list of {url, title, snippet, source}.
    """
    return await _search(query, min(max(count, 1), 10))
