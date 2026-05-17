"""LangChain tools used by the LangGraph agents.

Each public symbol here is a `@tool`-decorated callable that the LLM can
invoke by name. Keep tool docstrings short and unambiguous — the LLM reads
them as the tool's API contract.
"""
from app.tools.bing_search import bing_search
from app.tools.fetch_url import fetch_url
from app.tools.google_search import google_search
from app.tools.wikipedia_search import wikipedia_search

ALL_SEARCH_TOOLS = [google_search, bing_search, wikipedia_search]
ALL_TOOLS = [*ALL_SEARCH_TOOLS, fetch_url]

__all__ = [
    "ALL_SEARCH_TOOLS",
    "ALL_TOOLS",
    "bing_search",
    "fetch_url",
    "google_search",
    "wikipedia_search",
]
