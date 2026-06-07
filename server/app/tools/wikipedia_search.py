"""Wikipedia search via the MediaWiki full-text search API."""

from __future__ import annotations

import asyncio
import html
import re

from langchain_core.tools import tool
from mediawiki import MediaWiki, MediaWikiException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.tools.sources import SearchHit

_wiki = MediaWiki(user_agent="fact-checking-tool/1.0")

# The search API returns snippets as HTML (highlight <span>s + escaped entities).
_TAGS = re.compile(r"<[^>]+>")
def _clean(snippet: str) -> str:
    return html.unescape(_TAGS.sub("", snippet)).strip()


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(MediaWikiException),
)
def _search_sync(query: str, count: int) -> list[SearchHit]:
    # Call the action API directly rather than _wiki.search() to get the snippet;
    # titles have no URL field, hence reconstructing the canonical article URL.
    resp = _wiki.wiki_request(
        {
            "action": "query", 
            "list": "search", 
            "srsearch": query, 
            "srlimit": count, 
            "format": "json"
        }
    )
    hits: list[SearchHit] = []
    for r in resp.get("query", {}).get("search", []):
        title = r["title"]
        if "disambiguation" in title.lower():
            continue
        url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        hits.append(
            SearchHit(url=url, title=title, snippet=_clean(r.get("snippet", "")), source="wikipedia")
        )
    return hits


@tool
async def wikipedia_search(query: str, count: int = 3) -> list[SearchHit]:
    """Search Wikipedia for articles relevant to the query.

    Best for: encyclopedic facts, historical events, well-established topics.
    Skips disambiguation pages automatically. Returns up to `count` hits.
    """
    return await asyncio.to_thread(_search_sync, query, min(max(count, 1), 10))
