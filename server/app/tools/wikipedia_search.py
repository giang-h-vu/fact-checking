"""Wikipedia search via the MediaWiki opensearch API."""

from __future__ import annotations

from langchain_core.tools import tool
from mediawiki import MediaWiki, MediaWikiException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.tools.sources import SearchHit

_wiki = MediaWiki(user_agent="fact-checking-tool/1.0")


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(MediaWikiException),
)
def _search(query: str, count: int) -> list[SearchHit]:
    raw = _wiki.opensearch(query, results=count)  # [(title, summary, url), ...]
    hits: list[SearchHit] = []
    for title, summary, url in raw:
        if "disambiguation" in title.lower():
            continue
        hits.append(SearchHit(url=url, title=title, snippet=summary, source="wikipedia"))
    return hits


@tool
def wikipedia_search(query: str, count: int = 5) -> list[SearchHit]:
    """Search Wikipedia for articles relevant to the query.

    Best for: encyclopedic facts, historical events, well-established topics.
    Skips disambiguation pages automatically. Returns up to `count` hits.
    """
    return _search(query, min(max(count, 1), 10))
