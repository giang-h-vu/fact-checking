"""LangSmith tracing: off by default, and raw page text never reaches a trace."""

import json

from langchain_core.load import dumpd
from langchain_core.messages import HumanMessage
from langchain_core.tracers.langchain import LangChainTracer

from app.agents.evidence_retrieval import PASSAGE_PROMPT
from app.platform import tracing
from app.platform.config import Settings
from app.tools import fetch_url
from app.tools.sources import FetchedPage

ARTICLE = "SECRET-ARTICLE-BODY " * 50


def test_scrubber_header_matches_prompt():
    assert tracing.ARTICLE_HEADER in PASSAGE_PROMPT


def test_scrub_drops_article_keeps_claim():
    prompt = PASSAGE_PROMPT.format(claim="The sky is blue", article=ARTICLE)
    # same nesting LangSmith sees for a chat-model run
    inputs = {"messages": [[dumpd(HumanMessage(content=prompt))]]}

    out = json.dumps(tracing._scrub(inputs))

    assert "SECRET-ARTICLE-BODY" not in out
    assert "The sky is blue" in out
    assert "raw page text omitted" in out


def test_fetched_page_text_excluded_from_repr():
    page = FetchedPage(url="http://x", title="T", text=ARTICLE)

    assert "SECRET-ARTICLE-BODY" not in str(page)
    assert page.text == ARTICLE  # still available to callers


def test_disabled_by_default():
    assert tracing.trace_config(1, "auto") == {}


def test_enabled_registers_scrubbing_tracer(monkeypatch):
    monkeypatch.setattr(
        tracing,
        "get_settings",
        lambda: Settings(langsmith_tracing=True, langsmith_api_key="k", _env_file=None),
    )
    tracing._client.cache_clear()
    try:
        cfg = tracing.trace_config(7, "wiki")
        (tracer,) = cfg["callbacks"]
        assert isinstance(tracer, LangChainTracer)
        assert cfg["metadata"] == {"user_id": 7, "prefer_source": "wiki"}
    finally:
        tracing._client.cache_clear()


async def test_real_fetch_output_has_no_page_text():
    """Hits the real network (like test_tools): example.com is stable."""
    page = await fetch_url.ainvoke({"url": "https://example.com"})

    assert page.text, "fetch returned no text; test would be vacuous"
    assert page.text[:40] not in str(page)
