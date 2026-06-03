"""Google Custom Search wrapped as a LangChain tool.
"""
from __future__ import annotations

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.platform.config import get_settings
from app.tools.sources import SearchHit


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(HttpError),
)
def _search(query: str, count: int) -> list[SearchHit]:
    settings = get_settings()
    if not settings.google_api_key or not settings.google_cse_id:
        raise RuntimeError("GOOGLE_API_KEY and GOOGLE_CSE_ID must be set in .env")

    service = build("customsearch", "v1", developerKey=settings.google_api_key)
    response = (
        service.cse()
        .list(
            q=query,
            cx=settings.google_cse_id,
            num=count,
            c2coff="1",
            fields="items(title,link,snippet)",
        )
        .execute()
    )
    items = response.get("items") or []
    return [
        SearchHit(
            url=item["link"], 
            title=item.get("title", ""), 
            snippet=item.get("snippet", ""), 
            source="google"
        )
        for item in items
    ]


@tool
def google_search(query: str, count: int = 5) -> list[SearchHit]:
    """Search Google for the given query and return up to `count` web results.

    Best for: general web evidence, news, blog posts, current events.
    Returns: list of {url, title, snippet, source}.
    """
    return _search(query, min(max(count, 1), 10))
