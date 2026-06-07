"""LangChain tools used by the LangGraph agents.

Each public symbol here is a `@tool`-decorated callable that the LLM can
invoke by name. Keep tool docstrings short and unambiguous — the LLM reads
them as the tool's API contract.
"""

from langchain_core.tools import BaseTool

from app.tools.brave_search import brave_search
from app.tools.duckduckgo_search import duckduckgo_search
from app.tools.fetch_url import fetch_url
from app.tools.sources import SearchSource
from app.tools.wikipedia_search import wikipedia_search

# Single source of truth for search engine name → tool mapping.
# Add a new engine here; everything else derives from this dict.
SEARCH_SOURCES: dict[SearchSource, BaseTool] = {
    "duckduckgo": duckduckgo_search,
    "brave": brave_search,
    "wikipedia": wikipedia_search,
}

__all__ = [
    "SEARCH_SOURCES",
    "brave_search",
    "duckduckgo_search",
    "fetch_url",
    "wikipedia_search",
]
