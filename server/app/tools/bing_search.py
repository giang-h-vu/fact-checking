"""Bing Web Search v7 wrapped as a LangChain tool."""

from __future__ import annotations

import httpx
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.platform.config import get_settings
from app.tools.sources import SearchHit

BING_URL = "https://api.bing.microsoft.com/v7.0/search"


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
def _search(query: str, count: int) -> list[SearchHit]:
    settings = get_settings()
    if not settings.bing_api_key:
        raise RuntimeError("BING_API_KEY must be set in .env")

    response = httpx.get(
        BING_URL,
        headers={"Ocp-Apim-Subscription-Key": settings.bing_api_key},
        params={
            "q": query,
            "count": count,
            "textDecorations": False,
            "textFormat": "Raw",
            "responseFilter": "Webpages",
        },
        timeout=settings.http_timeout_seconds,
    )
    response.raise_for_status()
    pages = response.json().get("webPages", {}).get("value", [])
    return [
        SearchHit(
            url=p["url"], title=p.get("name", ""), snippet=p.get("snippet", ""), source="bing"
        )
        for p in pages
    ]


@tool
def bing_search(query: str, count: int = 3) -> list[SearchHit]:
    """Search Bing for the given query and return up to `count` web results.

    Best for: general web evidence; complements Google when results are sparse.
    Returns: list of {url, title, snippet, source}.
    """
    return _search(query, min(max(count, 1), 10))
