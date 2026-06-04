"""Integration tests for the agent tools.

Per .claude/rules/microservices.md: "Write integration and E2E tests that hit
a real database and external APIs — not mocks." Wikipedia and fetch_url hit
public endpoints unconditionally; Google/Bing skip when no API key is in env.
"""

from __future__ import annotations

import pytest

from app.platform.config import get_settings
from app.tools import bing_search, fetch_url, google_search, wikipedia_search

WIKI_EIFFEL_URL = "https://en.wikipedia.org/wiki/Eiffel_Tower"


def _invoke(tool, **kwargs):
    """LangChain tools are BaseTool instances — call via .invoke."""
    return tool.invoke(kwargs)


class TestWikipediaSearch:
    def test_returns_eiffel_tower_for_obvious_query(self):
        hits = _invoke(wikipedia_search, query="Eiffel Tower", count=5)
        assert len(hits) > 0
        assert any("Eiffel" in h["title"] for h in hits)
        assert all(h["source"] == "wikipedia" for h in hits)
        assert all(h["url"].startswith("http") for h in hits)

    def test_disambiguation_pages_filtered(self):
        # "Mercury" famously has a disambiguation page.
        hits = _invoke(wikipedia_search, query="Mercury", count=10)
        assert all("disambiguation" not in h["title"].lower() for h in hits)


class TestFetchUrl:
    def test_extracts_main_text_from_wikipedia(self):
        page = _invoke(fetch_url, url=WIKI_EIFFEL_URL)
        assert page["url"] == WIKI_EIFFEL_URL
        assert "Eiffel" in page["text"]
        assert "Main page" not in page["text"][:500]


class TestGoogleSearch:
    def setup_method(self):
        settings = get_settings()
        if not settings.google_api_key or not settings.google_cse_id:
            pytest.skip("GOOGLE_API_KEY / GOOGLE_CSE_ID not configured")

    def test_returns_results(self):
        hits = _invoke(google_search, query="Eiffel Tower height", count=3)
        assert len(hits) > 0
        assert all(h["source"] == "google" for h in hits)


class TestBingSearch:
    def setup_method(self):
        if not get_settings().bing_api_key:
            pytest.skip("BING_API_KEY not configured")

    def test_returns_results(self):
        hits = _invoke(bing_search, query="Eiffel Tower height", count=3)
        assert len(hits) > 0
        assert all(h["source"] == "bing" for h in hits)
