"""Integration tests for the agent tools.
Wikipedia, DuckDuckGo and fetch_url hit public endpoints unconditionally; 
Brave skips when no API key is in env.

Tools are async LangChain tools, so they are exercised via ``.ainvoke`` and
return their Pydantic models.
"""

from __future__ import annotations

import pytest

from app.platform.config import get_settings
from app.tools import brave_search, duckduckgo_search, fetch_url, wikipedia_search

WIKI_EIFFEL_URL = "https://en.wikipedia.org/wiki/Eiffel_Tower"


class TestWikipediaSearch:
    async def test_returns_eiffel_tower_for_obvious_query(self):
        hits = await wikipedia_search.ainvoke({"query": "Eiffel Tower", "count": 5})
        assert len(hits) > 0
        assert any("Eiffel" in h.title for h in hits)
        assert all(h.source == "wikipedia" for h in hits)
        assert all(h.url.startswith("http") for h in hits)

    async def test_disambiguation_pages_filtered(self):
        # "Mercury" famously has a disambiguation page.
        hits = await wikipedia_search.ainvoke({"query": "Mercury", "count": 10})
        assert all("disambiguation" not in h.title.lower() for h in hits)


class TestDuckDuckGoSearch:
    async def test_returns_results(self):
        hits = await duckduckgo_search.ainvoke({"query": "Eiffel Tower height", "count": 3})
        assert len(hits) > 0
        assert all(h.source == "duckduckgo" for h in hits)
        assert all(h.url.startswith("http") for h in hits)


class TestBraveSearch:
    def setup_method(self):
        if not get_settings().brave_api_key:
            pytest.skip("BRAVE_API_KEY not configured")

    async def test_returns_results(self):
        hits = await brave_search.ainvoke({"query": "Eiffel Tower height", "count": 3})
        assert len(hits) > 0
        assert all(h.source == "brave" for h in hits)


class TestFetchUrl:
    async def test_extracts_main_text_from_wikipedia(self):
        page = await fetch_url.ainvoke({"url": WIKI_EIFFEL_URL})
        assert page.url == WIKI_EIFFEL_URL
        assert "Eiffel" in page.text
        assert "Main page" not in page.text[:500]
