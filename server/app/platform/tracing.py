"""Opt-in LangSmith tracing that never uploads raw page content.

Disabled unless `LANGSMITH_TRACING=true` and a key are set. The tracer is built
explicitly (not via LangChain's env-var auto-tracing) so the scrubbing client is
always the one in use.

Raw fetched pages can reach a trace in exactly two places, both closed here:
  * `fetch_url` output   -> `FetchedPage.text` is excluded from repr (tools/sources.py).
  * extraction LLM input -> `_scrub` cuts the prompt after `ARTICLE_HEADER`.
Only the extracted `Passage` text is ever traced.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client

from app.platform.config import get_settings

# Must match the header in evidence_retrieval.PASSAGE_PROMPT (tests/test_tracing.py checks).
ARTICLE_HEADER = "Article (truncated):\n"


def _scrub(value: Any) -> Any:
    """Replace everything after ARTICLE_HEADER in any string nested in a run's inputs."""
    if isinstance(value, str):
        head, sep, rest = value.partition(ARTICLE_HEADER)
        return f"{head}{sep}[raw page text omitted: {len(rest)} chars]" if sep else value
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


@lru_cache
def _client() -> Client:
    s = get_settings()
    assert s.langsmith_api_key is not None
    return Client(
        api_key=s.langsmith_api_key.get_secret_value(),
        api_url=s.langsmith_endpoint or None,
        hide_inputs=_scrub,
    )


def trace_config(user_id: int, prefer_source: str) -> RunnableConfig:
    """Config to pass to graph.astream/ainvoke; empty (no tracing) unless enabled."""
    s = get_settings()
    if not (s.langsmith_tracing and s.langsmith_api_key):
        return {}
    # call tracer.wait_for_futures() in a lifespan hook if that matters.
    return {
        "callbacks": [LangChainTracer(client=_client(), project_name=s.langsmith_project)],
        "run_name": "fact-check",
        "metadata": {"user_id": user_id, "prefer_source": prefer_source},
    }
