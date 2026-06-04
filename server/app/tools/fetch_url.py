"""Fetch a URL and extract clean main text."""

from __future__ import annotations

import httpx
import trafilatura
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.platform.config import get_settings
from app.tools.sources import FetchedPage

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; fact-checking-tool/1.0;"),
}


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
)
async def _fetch_html(url: str) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        response = await client.get(url, timeout=settings.http_timeout_seconds)
        response.raise_for_status()
        return response.text


@tool
async def fetch_url(url: str) -> FetchedPage:
    """Fetch a URL and return its main article text (boilerplate stripped).

    Use this on a URL produced by one of the search tools. Returns
    {url, title, text}; `text` may be empty if the page wasn't extractable
    """
    html = await _fetch_html(url)
    extracted = (
        trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        or ""
    )
    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata and metadata.title else "") or ""

    return FetchedPage(url=url, title=title, text=extracted)
