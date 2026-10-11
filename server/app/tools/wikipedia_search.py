"""Wikipedia search via the MediaWiki full-text search API."""

from __future__ import annotations

import asyncio
import html
import re
from functools import lru_cache

from langchain_core.tools import tool
from mediawiki import MediaWiki
from mediawiki.exceptions import MediaWikiException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.tools.sources import SearchHit


@lru_cache(maxsize=1)
def _client() -> MediaWiki:
    # Built on first use: the constructor calls the API, and doing that at import made
    # a throttled Wikipedia break importing app.tools (and test collection). A failure
    # is not cached, so the next search retries it.
    return MediaWiki(user_agent="fact-checking-tool/1.0")


# The search API returns snippets as HTML (highlight <span>s + escaped entities).
_TAGS = re.compile(r"<[^>]+>")


def _clean(snippet: str) -> str:
    return html.unescape(_TAGS.sub("", snippet)).strip()


# One more try on a network blip (requests' ConnectionError/Timeout are OSErrors). Not on
# an empty or error answer: a 429 page answers the same again, and the caller has a fallback.
@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(OSError),
)
def _search_sync(query: str, count: int) -> list[SearchHit]:
    # Call the action API directly rather than _client().search() to get the snippet;
    # titles have no URL field, hence reconstructing the canonical article URL.
    resp = _client().wiki_request(
        {"action": "query", "list": "search", "srsearch": query, "srlimit": count, "format": "json"}
    )
    # wiki_request returns {} for a non-JSON reply (a 429 page) and {"error": ...} for an API error
    #  Raise so the caller can tell a failed search from one that found nothing.
    if "query" not in resp:
        info = resp.get("error", {}).get("info", "empty response")
        raise MediaWikiException(f"Wikipedia search failed: {info}")
    hits: list[SearchHit] = []
    for r in resp["query"].get("search", []):
        title = r["title"]
        if "disambiguation" in title.lower():
            continue
        url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        hits.append(
            SearchHit(
                url=url, title=title, snippet=_clean(r.get("snippet", "")), source="wikipedia"
            )
        )
    return hits


@tool
async def wikipedia_search(query: str, count: int = 3) -> list[SearchHit]:
    """Search Wikipedia for articles relevant to the query. Skips disambiguation pages."""
    return await asyncio.to_thread(_search_sync, query, min(max(count, 1), 10))
