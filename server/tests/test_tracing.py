"""LangSmith tracing: off by default, and raw page text never reaches a trace."""

import json

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.load import dumpd
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tracers.langchain import LangChainTracer

from app.agents import claim_verification
from app.agents.claim_verification import JudgeOutput, verify_subclaims
from app.agents.evidence_retrieval import PASSAGE_PROMPT
from app.domain.state import Verdict
from app.platform import tracing
from app.platform.config import Settings
from app.tools import fetch_url
from app.tools.sources import FetchedPage, Passage

ARTICLE = "SECRET-ARTICLE-BODY " * 50


def test_scrubber_header_matches_prompt():
    assert tracing.ARTICLE_HEADER in PASSAGE_PROMPT


def test_scrub_drops_article_keeps_claim():
    prompt = PASSAGE_PROMPT.format(claim="The sky is blue", focus="", article=ARTICLE)
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


class _Tree(BaseCallbackHandler):
    """Records the run tree: parent of each run, name of each run, and errored runs."""

    def __init__(self):
        self.parent, self.name, self.errored = {}, {}, []

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self.parent[run_id] = parent_run_id
        self.name[run_id] = kwargs.get("name") or (serialized or {}).get("name")

    def on_chain_error(self, error, *, run_id, **kwargs):
        self.errored.append(run_id)


def _judge_says_supported(monkeypatch) -> None:
    class Model:
        def with_structured_output(self, *a, **k):
            return RunnableLambda(lambda _: JudgeOutput(label=Verdict.SUPPORTED, reasoning="r"))

    monkeypatch.setattr(claim_verification, "get_llm", lambda: Model())


async def test_verification_nests_under_the_fact_check_run(monkeypatch):
    """The judge calls used to be root traces of their own, apart from the research."""
    _judge_says_supported(monkeypatch)
    tree = _Tree()

    async with tracing.fact_check_run("c", {"callbacks": [tree]}) as cfg:
        await verify_subclaims(["a"], [[Passage(url="u", title="t", text="p")]], cfg)

    roots = [r for r, parent in tree.parent.items() if parent is None]
    assert [tree.name[r] for r in roots] == ["fact-check"]
    assert len(tree.parent) > 1  # the judge ran, and inside that root


async def test_a_failed_run_is_closed_as_an_error():
    tree = _Tree()

    with pytest.raises(RuntimeError):
        async with tracing.fact_check_run("c", {"callbacks": [tree]}):
            raise RuntimeError("boom")

    (root,) = (r for r, parent in tree.parent.items() if parent is None)
    assert tree.errored == [root]


async def test_no_parent_run_when_tracing_is_off():
    async with tracing.fact_check_run("c", {}) as cfg:
        assert cfg == {}


async def test_real_fetch_output_has_no_page_text():
    """Hits the real network (like test_tools): example.com is stable."""
    page = await fetch_url.ainvoke({"url": "https://example.com"})

    assert page.text, "fetch returned no text; test would be vacuous"
    assert page.text[:40] not in str(page)
