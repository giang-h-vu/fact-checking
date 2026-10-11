"""LangChain tools used by the research agents.

Only `think_tool` is bound to a model. The search tools and `fetch_url` are called from
Python (`researcher.run_queries` / `fetch_page`), so their docstrings are not prompts;
what the models read about engines is in the orchestrator prompt and `SearchQuery`.
"""

from langchain_core.tools import BaseTool

from app.tools.brave_search import brave_search
from app.tools.duckduckgo_search import duckduckgo_search
from app.tools.fetch_url import fetch_url
from app.tools.sources import SearchSource
from app.tools.think import think_tool
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
    "think_tool",
    "wikipedia_search",
]
