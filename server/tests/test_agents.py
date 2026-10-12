"""Research agents: tool contracts, state wiring, bounds, and context isolation.

One tool test hits the real network (Wikipedia), like test_tools. The wiring tests
drive the real graphs with a scripted chat model and a stubbed network layer. The
end-to-end test makes real LLM calls (roughly 30 per run), so it is opt-in:
RUN_LLM_TESTS=1.
"""

import asyncio
import glob
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt.tool_node import ToolRuntime

from app.agents import claim_verification, evidence_retrieval, orchestrator, researcher
from app.agents.claim_verification import combine_verdicts, verify_subclaims
from app.agents.evidence_retrieval import (
    PAGE_CHAR_LIMIT,
    PassageExtraction,
    best_excerpt,
    keep_verbatim,
)
from app.agents.run import (
    CombinedEvidence,
    Ctx,
    FileRef,
    PassageFound,
    PlanCreated,
    ResearchDone,
    SearchQuery,
    SearchRan,
    add_counts,
    available_engines,
    merge_pages,
    merge_passages,
)
from app.domain.state import Verdict
from app.platform.config import Settings, get_settings
from app.tools import think_tool
from app.tools.sources import FetchedPage, Passage, SearchHit


def make_runtime(tmp_path: Path, state: dict[str, Any] | None = None, **settings: Any):
    """A `ToolRuntime` as the graph would inject it, plus the events written to it."""
    events: list[Any] = []
    ctx = Ctx(
        settings=Settings(**settings),
        engines=["wikipedia", "duckduckgo"],
        workdir=tmp_path,
        fetch_sem=asyncio.Semaphore(3),
    )
    runtime = ToolRuntime(
        state=state or {},
        context=ctx,
        config={},
        stream_writer=events.append,
        tool_call_id="call-1",
        store=None,
    )
    return runtime, events


def researcher_state(**overrides: Any) -> dict[str, Any]:
    return {
        "subclaim": "The Eiffel Tower is in Paris",
        "todo_id": 0,
        "seen_urls": [],
        "files": {},
        "fetched": [],
        "passages": [],
        **overrides,
    }


def reply_text(result: Any) -> str:
    """The tool message text, whether the tool returned a str or a Command."""
    if isinstance(result, str):
        return result
    return str(result.update["messages"][0].content)


class TestAvailableEngines:
    def test_wiki_hint_is_wikipedia_only(self):
        assert available_engines("wiki", "key") == ["wikipedia"]

    def test_web_hint_excludes_wikipedia(self):
        assert available_engines("web", "") == ["duckduckgo"]
        assert available_engines("web", "key") == ["brave", "duckduckgo"]

    def test_auto_has_everything_configured(self):
        assert available_engines("auto", "") == ["wikipedia", "duckduckgo"]
        assert available_engines("auto", "key") == ["wikipedia", "brave", "duckduckgo"]


class TestStateReducers:
    def test_passages_merge_per_todo(self):
        a, b, c = (Passage(url=u, title="", text=u) for u in "abc")
        merged = merge_passages({0: [a], 1: [b]}, {0: [c]})
        assert merged == {0: [a, c], 1: [b]}

    def test_counts_add(self):
        assert add_counts({0: 1}, {0: 1, 2: 1}) == {0: 2, 2: 1}

    def test_pages_merge_without_repeats(self):
        assert merge_pages({0: ["p1", "p2"]}, {0: ["p2", "p3"], 1: ["p9"]}) == {
            0: ["p1", "p2", "p3"],
            1: ["p9"],
        }


class TestToolSchemas:
    def test_delegate_takes_queries_with_engines_and_a_focus_and_combined(self):
        schema = orchestrator.delegate.tool_call_schema.model_json_schema()
        props = schema["properties"]
        assert set(props) == {"todo_id", "queries", "focus", "combined"}
        assert "counting from 1" in props["todo_id"]["description"]
        assert "comparison" in props["combined"]["description"]
        assert "runtime" not in props  # injected, never shown to the model
        engines = schema["$defs"]["SearchQuery"]["properties"]["engine"]["enum"]
        assert set(engines) == {"wikipedia", "brave", "duckduckgo"}

    def test_extract_passage_exposes_page_and_focus_only(self):
        props = researcher.extract_passage.tool_call_schema.model_json_schema()["properties"]
        assert set(props) == {"page_id", "focus"}
        assert all("description" in p for p in props.values())

    def test_search_is_not_a_model_tool(self):
        names = {t.name for t in researcher.SEARCH_TOOLS + researcher.REEXTRACT_TOOLS}
        assert names == {"fetch_page", "extract_passage"}  # reflection is the orchestrator's
        assert {t.name for t in researcher.REEXTRACT_TOOLS} == {"extract_passage"}


class TestVerbatimGuard:
    ARTICLE = "The tower was built in 1889.\nIt is “330 m” tall – a record."

    def test_verbatim_passage_is_kept(self):
        assert keep_verbatim("The tower was built in 1889.", self.ARTICLE) == (
            "The tower was built in 1889."
        )

    def test_invented_part_is_dropped(self):
        got = keep_verbatim("The tower was built in 1889. ... It is made of cheese.", self.ARTICLE)
        assert got == "The tower was built in 1889."

    def test_nothing_verbatim_is_none(self):
        assert keep_verbatim("Paris is the capital.", self.ARTICLE) is None

    def test_quote_and_whitespace_variants_still_match(self):
        assert keep_verbatim('It is "330 m" tall - a record.', self.ARTICLE) is not None

    def test_footnote_markers_and_table_pipes_are_ignored(self):
        article = "A federal republic[1] of 50 states.[2][3]\nAlabama | Montgomery | 1819 |"
        assert keep_verbatim("A federal republic of 50 states.", article) is not None
        assert keep_verbatim("Alabama Montgomery 1819", article) is not None


class TestBestExcerpt:
    LEAD = "Overview of a very long page."
    FACT = "Marie Curie won the Nobel Prize in 1911."

    def page(self, fact_at: int, lines: int = 400) -> str:
        filler = [
            f"Filler line {i} about gardening, weather and other unrelated things."
            for i in range(lines)
        ]
        filler[0] = self.LEAD
        filler[fact_at] = self.FACT
        return "\n".join(filler)

    def test_short_page_is_returned_whole(self):
        assert best_excerpt("short page", "anything") == "short page"

    def test_fact_deep_in_a_long_page_is_found(self):
        text = self.page(fact_at=350)
        assert text.index(self.FACT) > PAGE_CHAR_LIMIT  # first-10k would have missed it

        excerpt = best_excerpt(text, "Nobel Prize 1911")

        assert self.FACT in excerpt
        assert len(excerpt) <= PAGE_CHAR_LIMIT

    def test_lead_is_kept_and_order_is_the_pages(self):
        excerpt = best_excerpt(self.page(fact_at=350), "Nobel Prize 1911")
        assert excerpt.startswith(self.LEAD)
        assert excerpt.index(self.LEAD) < excerpt.index(self.FACT)

    def test_a_new_focus_selects_different_lines(self):
        text = self.page(fact_at=350)
        text += "\nThe laureate was awarded the medal in Stockholm by the king."
        a = best_excerpt(text, "Nobel Prize 1911")
        b = best_excerpt(text, "Stockholm king medal")
        assert self.FACT in a and "Stockholm" not in a
        assert "Stockholm" in b

    def test_no_overlap_falls_back_to_the_start_of_the_page(self):
        text = self.page(fact_at=350)
        excerpt = best_excerpt(text, "zzzz qqqq")
        assert text.startswith(excerpt[:200]) and self.FACT not in excerpt

    def test_one_giant_line_respects_the_budget(self):
        assert len(best_excerpt("x" * (3 * PAGE_CHAR_LIMIT), "x")) <= PAGE_CHAR_LIMIT

    def test_blank_long_page_is_empty(self):
        assert best_excerpt(" \n" * PAGE_CHAR_LIMIT, "x") == ""


class TestExtractionFailures:
    PAGE = FetchedPage(url="u", title="t", text="The tower is in Paris.")

    def model_raising(self, monkeypatch, exc: Exception) -> None:
        def boom(_):
            raise exc

        class Model:
            def with_structured_output(self, *a, **k):
                return RunnableLambda(boom)

        monkeypatch.setattr(evidence_retrieval, "get_llm", lambda: Model())

    @pytest.mark.parametrize("exc", [OutputParserException("not json"), ValueError("bad")])
    async def test_an_unusable_answer_is_no_passage(self, monkeypatch, exc):
        self.model_raising(monkeypatch, exc)

        assert await evidence_retrieval.extract_passage_text("claim", self.PAGE) is None

    async def test_a_provider_error_is_not_no_passage(self, monkeypatch):
        self.model_raising(monkeypatch, RuntimeError("quota exceeded"))

        with pytest.raises(RuntimeError, match="quota exceeded"):
            await evidence_retrieval.extract_passage_text("claim", self.PAGE)


class TestJudgeFailures:
    def model_raising(self, monkeypatch, exc: Exception) -> None:
        def boom(_):
            raise exc

        class Model:
            def with_structured_output(self, *a, **k):
                return RunnableLambda(boom)

        monkeypatch.setattr(claim_verification, "get_llm", lambda: Model())

    @pytest.mark.parametrize("exc", [OutputParserException("not json"), ValueError("bad")])
    async def test_an_unusable_answer_is_not_enough_info(self, monkeypatch, exc):
        self.model_raising(monkeypatch, exc)

        label, reasoning = await claim_verification._judge("claim", "passage")

        assert label == Verdict.NOT_ENOUGH_INFO and "malformed" in reasoning

    async def test_a_provider_error_is_not_a_verdict(self, monkeypatch):
        self.model_raising(monkeypatch, RuntimeError("quota exceeded"))

        with pytest.raises(RuntimeError, match="quota exceeded"):
            await verify_subclaims(["a"], [[Passage(url="u", title="t", text="p")]])


class TestCombinedJudging:
    """A sub-claim marked `combined` is judged once over all its passages together."""

    PASSAGES = [
        Passage(url="v", title="Vietnam", text="Vietnam has over 102 million people."),
        Passage(url="n", title="Nigeria", text="Nigeria has more than 242 million people."),
    ]

    def judge_recording(self, monkeypatch) -> list[str]:
        prompts: list[str] = []

        def answer(messages):
            prompts.append(str(messages[-1].content))
            joint = "TAKEN TOGETHER" in str(messages[0].content)
            label = Verdict.REFUTED if joint else Verdict.NOT_ENOUGH_INFO
            return claim_verification.JudgeOutput(label=label, reasoning="r")

        class Model:
            def with_structured_output(self, *a, **k):
                return RunnableLambda(answer)

        monkeypatch.setattr(claim_verification, "get_llm", lambda: Model())
        return prompts

    async def test_a_marked_subclaim_is_judged_once_with_every_passage(self, monkeypatch):
        prompts = self.judge_recording(monkeypatch)

        out = await verify_subclaims(["Vietnam > Nigeria"], [self.PASSAGES], combined=[True])

        assert len(prompts) == 1 and "[1] Vietnam" in prompts[0] and "[2] Nigeria" in prompts[0]
        assert [v.label for v in out.passage_verdicts] == [Verdict.REFUTED] * 2
        assert out.final_verdict == Verdict.REFUTED and len(out.citations) == 2

    async def test_unmarked_subclaims_keep_the_per_passage_vote(self, monkeypatch):
        prompts = self.judge_recording(monkeypatch)

        out = await verify_subclaims(["Vietnam > Nigeria"], [self.PASSAGES])

        assert len(prompts) == 2
        assert out.final_verdict == Verdict.NOT_ENOUGH_INFO

    async def test_a_marked_subclaim_without_passages_needs_no_llm(self):
        out = await verify_subclaims(["a"], [[]], combined=[True])
        assert out.final_verdict == Verdict.NOT_ENOUGH_INFO


class TestOrchestratorTools:
    TODO = {"content": "c", "status": "pending"}
    QUERIES = [SearchQuery(query="q", engine="wikipedia")]

    async def call(self, runtime, **kwargs):
        return await orchestrator.delegate.coroutine(1, runtime, **kwargs)  # type: ignore[misc]

    async def test_delegate_needs_a_plan(self, tmp_path):
        runtime, _ = make_runtime(tmp_path)
        assert "write_todos first" in await self.call(runtime, queries=self.QUERIES)

    async def test_delegate_rejects_unknown_id_and_blank_todos(self, tmp_path):
        todos = [
            {"content": "only one", "status": "pending"},
            {"content": " ", "status": "pending"},
        ]
        runtime, _ = make_runtime(tmp_path, {"todos": todos})
        out = await orchestrator.delegate.coroutine(2, runtime, self.QUERIES)  # type: ignore[misc]
        assert "Unknown todo_id 2" in out and "1 to 1" in out

    async def test_extra_queries_are_ignored_and_the_model_is_told(self, tmp_path, monkeypatch):
        got: dict[str, Any] = {}

        async def fake(ctx, subclaim, idx, *, queries, **kw):
            got["queries"] = queries
            return researcher.Researched("summary", {}, [], [])

        monkeypatch.setattr(orchestrator, "run_researcher", fake)
        runtime, _ = make_runtime(tmp_path, {"todos": [self.TODO]})
        five = [SearchQuery(query=str(i), engine="wikipedia") for i in range(5)]

        out = await self.call(runtime, queries=five)

        assert orchestrator.MAX_QUERIES == 3 and len(got["queries"]) == 3
        text = str(out.update["messages"][0].content)
        assert text.startswith("(Only the first 3 queries ran; 2 ignored.)")
        assert text.endswith("summary\nRetries left for this todo: 2.")  # first of 1 + 2

    async def test_combined_is_announced_only_for_an_accepted_call(self, tmp_path, monkeypatch):
        async def fake(*args, **kw):
            return researcher.Researched("summary", {}, [], [])

        monkeypatch.setattr(orchestrator, "run_researcher", fake)
        runtime, events = make_runtime(tmp_path, {"todos": [self.TODO]})

        assert "First attempt needs queries" in await self.call(runtime, combined=True)
        assert not any(isinstance(e, CombinedEvidence) for e in events)

        await self.call(runtime, queries=self.QUERIES, combined=True)
        assert CombinedEvidence(0) in events

    async def test_a_provider_error_is_not_swallowed(self, tmp_path, monkeypatch):
        async def boom(*args, **kw):
            raise RuntimeError("provider down")

        monkeypatch.setattr(orchestrator, "run_researcher", boom)
        runtime, _ = make_runtime(tmp_path, {"todos": [self.TODO]})

        with pytest.raises(RuntimeError, match="provider down"):
            await self.call(runtime, queries=self.QUERIES)

    async def test_delegate_respects_the_subclaim_cap(self, tmp_path):
        todos = [{"content": c, "status": "pending"} for c in "abc"]
        runtime, _ = make_runtime(tmp_path, {"todos": todos}, agent_max_subclaims=2)
        out = await orchestrator.delegate.coroutine(3, runtime, self.QUERIES)  # type: ignore[misc]
        assert "1 to 2" in out

    async def test_retry_limit_is_one_plus_max_retries(self, tmp_path):
        state = {"todos": [self.TODO], "delegations": {0: 3}}
        runtime, _ = make_runtime(tmp_path, state, agent_max_retries=2)
        assert "limit reached" in await self.call(runtime, queries=self.QUERIES)

    async def test_first_attempt_needs_queries(self, tmp_path):
        runtime, _ = make_runtime(tmp_path, {"todos": [self.TODO]})
        assert "First attempt needs queries" in await self.call(runtime, focus="year")

    async def test_retry_without_saved_pages_needs_queries(self, tmp_path):
        state = {"todos": [self.TODO], "delegations": {0: 1}}
        runtime, _ = make_runtime(tmp_path, state)
        assert "Nothing saved" in await self.call(runtime, focus="year")

    async def test_reextract_needs_a_focus(self, tmp_path):
        state = {"todos": [self.TODO], "delegations": {0: 1}, "pages": {0: ["p1"]}}
        runtime, _ = make_runtime(tmp_path, state)
        assert "needs a focus" in await self.call(runtime, focus="  ")


class TestSearchRunner:
    def ctx(self, tmp_path) -> Ctx:
        return make_runtime(tmp_path)[0].context

    async def test_unavailable_engine_is_replaced_by_one_of_the_same_kind(
        self, tmp_path, monkeypatch
    ):
        used: list[str] = []

        async def fake(engine, query, count):
            used.append(engine)
            return []

        monkeypatch.setattr(researcher, "_search", fake)
        events: list[Any] = []

        await researcher.run_queries(
            self.ctx(tmp_path), [SearchQuery(query="q", engine="brave")], events.append
        )

        # make_runtime offers wikipedia + duckduckgo: a brave (web) query must not
        # land on wikipedia
        assert used == ["duckduckgo"]
        assert len(events) == 1 and isinstance(events[0], SearchRan)

    def test_allowed_keeps_the_kind_and_degrades_to_the_first(self):
        allowed = researcher._allowed
        assert allowed("wikipedia", ["wikipedia"]) == "wikipedia"
        assert allowed("brave", ["wikipedia", "duckduckgo"]) == "duckduckgo"
        assert allowed("duckduckgo", ["wikipedia", "brave"]) == "brave"
        assert allowed("wikipedia", ["brave", "duckduckgo"]) == "brave"  # no encyclopedia: web
        assert allowed("brave", ["wikipedia"]) == "wikipedia"  # no web: the only engine

    def test_header_lists_every_saved_page_and_whether_it_gave_a_passage(self):
        files = {
            "p1": FileRef(url="https://a", title="A\n  Page", path="x"),
            "p2": FileRef(url="https://b", title="B" * 200, path="x"),
            "p3": FileRef(url="https://c", title="", path="x"),
        }
        got = Passage(url="https://a", title="A", text="t")

        header = researcher._header([got], ["p1", "p2", "p3", "gone"], files, [got])

        lines = header.split("\n")
        assert lines[0] == "1 passage(s) extracted from: https://a. 4 page(s) saved for this todo."
        assert lines[1] == "- A Page | https://a (passage extracted)"
        assert lines[2] == f"- {'B' * 80} | https://b (no passage)"  # one short line
        assert lines[3] == "- (untitled) | https://c (no passage)"
        assert len(lines) == 4  # an id with no file is counted, not listed

    async def test_queries_run_in_parallel_and_hits_are_merged_by_url(self, tmp_path, monkeypatch):
        async def fake(engine, query, count):
            return [
                SearchHit(url="https://a", title="A", snippet="", source=engine),
                SearchHit(url=f"https://{query}", title=query, snippet="", source=engine),
            ]

        monkeypatch.setattr(researcher, "_search", fake)
        queries = [SearchQuery(query=q, engine="wikipedia") for q in ("x", "y", "x")]
        events: list[Any] = []

        hits, errors = await researcher.run_queries(self.ctx(tmp_path), queries, events.append)

        assert [h.url for h in hits] == ["https://a", "https://x", "https://y"]
        assert errors == []
        assert [e.query for e in events] == ["x", "y"]  # the repeated query ran once

    def failing_engines(self, monkeypatch, failing: set[str]) -> list[str]:
        """Stub the engines: those in `failing` raise a 429, the others return one hit."""
        calls: list[str] = []

        class Engine:
            def __init__(self, name: str) -> None:
                self.name = name

            async def ainvoke(self, args):
                calls.append(self.name)
                if self.name in failing:
                    request = httpx.Request("GET", "https://engine.test")
                    raise httpx.HTTPStatusError(
                        "429", request=request, response=httpx.Response(429, request=request)
                    )
                return [SearchHit(url="https://d", title="D", snippet="", source="duckduckgo")]

        names = ("brave", "duckduckgo", "wikipedia")
        monkeypatch.setattr(researcher, "SEARCH_SOURCES", {n: Engine(n) for n in names})
        return calls

    async def test_failing_engine_falls_back_to_its_backup(self, tmp_path, monkeypatch):
        calls = self.failing_engines(monkeypatch, {"wikipedia"})

        hits, errors = await researcher.run_queries(
            self.ctx(tmp_path), [SearchQuery(query="q", engine="wikipedia")], lambda _: None
        )

        assert calls == ["wikipedia", "duckduckgo"]
        assert [h.url for h in hits] == ["https://d"] and errors == []

    async def test_failure_without_an_allowed_backup_is_reported_not_empty(
        self, tmp_path, monkeypatch
    ):
        calls = self.failing_engines(monkeypatch, {"wikipedia"})
        ctx = Ctx(
            settings=self.ctx(tmp_path).settings,
            engines=["wikipedia"],  # prefer_source="wiki": duckduckgo is not allowed
            workdir=tmp_path,
            fetch_sem=asyncio.Semaphore(1),
        )

        hits, errors = await researcher.run_queries(
            ctx, [SearchQuery(query="q", engine="wikipedia")], lambda _: None
        )

        assert calls == ["wikipedia"] and hits == []
        assert errors == ["'q': wikipedia rate limited"]

    async def test_failed_search_is_not_reported_as_no_results(self, tmp_path, monkeypatch):
        self.failing_engines(monkeypatch, {"wikipedia", "duckduckgo"})

        result = await researcher.run_researcher(
            self.ctx(tmp_path),
            "claim",
            0,
            queries=[SearchQuery(query="q", engine="wikipedia")],
            focus="",
            files={},
            pages=[],
            passages=[],
            config={},
            emit=lambda _: None,
        )

        assert "Search failed" in result.summary and "Try another engine" in result.summary
        assert "No search results" not in result.summary

    def test_wikipedia_empty_response_is_a_failure_not_zero_hits(self, monkeypatch):
        import importlib

        from mediawiki.exceptions import MediaWikiException

        # `app.tools.wikipedia_search` the attribute is the tool; we need the module.
        wiki = importlib.import_module("app.tools.wikipedia_search")

        class Client:
            def __init__(self, resp: dict[str, Any]) -> None:
                self.resp = resp

            def wiki_request(self, params):
                return self.resp

        raw = wiki._search_sync
        monkeypatch.setattr(wiki, "_client", lambda: Client({}))
        with pytest.raises(MediaWikiException):
            raw("q", 3)
        monkeypatch.setattr(wiki, "_client", lambda: Client({"query": {"search": []}}))
        assert raw("q", 3) == []

    def test_wikipedia_retries_a_network_blip_but_not_an_empty_answer(self, monkeypatch):
        import importlib

        from mediawiki.exceptions import MediaWikiException
        from tenacity import wait_none

        wiki = importlib.import_module("app.tools.wikipedia_search")
        raw = wiki._search_sync
        monkeypatch.setattr(raw.retry, "wait", wait_none())  # no real sleep in the test
        calls: list[int] = []

        def client(answers):
            class Client:
                def wiki_request(self, params):
                    calls.append(1)
                    answer = answers.pop(0)
                    if isinstance(answer, Exception):
                        raise answer
                    return answer

            return Client()

        ok = {"query": {"search": []}}
        blip = client([ConnectionError("blip"), ok])  # one client: `_client()` runs per attempt
        monkeypatch.setattr(wiki, "_client", lambda: blip)
        assert raw("q", 3) == [] and len(calls) == 2  # retried once, then succeeded

        calls.clear()
        empty = client([{}, ok])
        monkeypatch.setattr(wiki, "_client", lambda: empty)
        with pytest.raises(MediaWikiException):
            raw("q", 3)
        assert len(calls) == 1  # an empty (429) answer is not retried


class TestRunResearcher:
    def ctx(self, tmp_path) -> Ctx:
        return make_runtime(tmp_path)[0].context

    def saved_pages(self, tmp_path, n: int, *, on_disk: bool = True) -> dict[str, FileRef]:
        files: dict[str, FileRef] = {}
        for i in range(n):
            path = tmp_path / f"p{i:08x}.txt"
            if on_disk:
                path.write_text(f"{REAL_SENTENCE} (page {i})", "utf-8")
            files[path.stem] = FileRef(
                url=f"https://example.org/{i}", title=f"T{i}", path=str(path)
            )
        return files

    async def rerun(self, ctx, files, **kw):
        return await researcher.run_researcher(
            ctx,
            "The Eiffel Tower is in Paris",
            0,
            queries=[],
            focus="height",
            files=files,
            pages=list(files),
            passages=[],
            config={},
            emit=lambda _: None,
            **kw,
        )

    async def test_focus_retry_rereads_only_the_most_recent_pages(self, tmp_path, monkeypatch):
        model = scripted()
        for module in (researcher, evidence_retrieval):
            monkeypatch.setattr(module, "get_llm", lambda: model)
        files = self.saved_pages(tmp_path, 6)

        result = await self.rerun(self.ctx(tmp_path), files)

        task = model.seen[0][1][1]
        listed = re.findall(r"- (p[0-9a-f]{8}) \|", task)
        assert listed == list(files)[-researcher.REEXTRACT_MAX_PAGES :]
        assert len(result.new_passages) == researcher.REEXTRACT_MAX_PAGES
        assert "6 page(s) saved" in result.summary  # the count is of all saved pages

    async def test_an_unreadable_saved_page_is_a_tool_error_not_a_failed_attempt(
        self, tmp_path, monkeypatch
    ):
        model = scripted()
        for module in (researcher, evidence_retrieval):
            monkeypatch.setattr(module, "get_llm", lambda: model)
        files = self.saved_pages(tmp_path, 2, on_disk=False)  # reading a page raises OSError

        result = await self.rerun(self.ctx(tmp_path), files)

        assert result.new_passages == [] and result.files == files
        assert "Research failed" not in result.summary
        assert "could not be read" in " ".join(" ".join(m) for _, m in model.seen)

    async def test_a_provider_error_ends_the_run(self, tmp_path, monkeypatch):
        class Down(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "down"

            def bind_tools(self, tools, **kwargs):
                return self

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                raise RuntimeError("provider down")

        monkeypatch.setattr(researcher, "get_llm", lambda: Down())

        with pytest.raises(RuntimeError, match="provider down"):
            await self.rerun(self.ctx(tmp_path), self.saved_pages(tmp_path, 1))


class TestResearcherTools:
    async def test_fetch_refuses_url_no_search_returned(self, tmp_path):
        runtime, _ = make_runtime(tmp_path, researcher_state())

        out = await researcher.fetch_page.coroutine(  # type: ignore[misc]
            "http://169.254.169.254/latest/meta-data", runtime
        )

        assert "not returned by a search" in out
        assert list(tmp_path.iterdir()) == []

    async def test_extract_refuses_unknown_page_id(self, tmp_path):
        runtime, _ = make_runtime(tmp_path, researcher_state())

        out = await researcher.extract_passage.coroutine("../../etc/passwd", runtime)  # type: ignore[misc]

        assert "Unknown page_id" in out

    async def test_second_extract_of_a_page_needs_a_focus(self, tmp_path):
        page = tmp_path / "p1.txt"
        page.write_text("text", "utf-8")
        state = researcher_state(
            files={"p1": FileRef(url="u", title="t", path=str(page))},
            passages=[Passage(url="u", title="t", text="earlier")],
        )
        runtime, _ = make_runtime(tmp_path, state)

        out = await researcher.extract_passage.coroutine("p1", runtime)  # type: ignore[misc]

        assert "already extracted" in out

    async def test_fetched_page_goes_to_file_not_to_the_model(self, tmp_path):
        """Real Wikipedia: search, then fetch the first hit."""
        runtime, events = make_runtime(tmp_path, researcher_state())
        query = SearchQuery(query="Eiffel Tower", engine="wikipedia")

        hits, errors = await researcher.run_queries(runtime.context, [query], events.append)
        assert hits, f"search returned nothing (errors: {errors})"
        runtime.state["seen_urls"] = [h.url for h in hits]

        fetched = await researcher.fetch_page.coroutine(hits[0].url, runtime)  # type: ignore[misc]

        ((page_id, ref),) = fetched.update["files"].items()
        text = Path(ref["path"]).read_text("utf-8")
        assert Path(ref["path"]).parent == tmp_path
        assert text, "fetched page was empty; test would be vacuous"
        assert text[:60] not in reply_text(fetched)
        assert page_id in reply_text(fetched)
        assert fetched.update["fetched"] == [page_id]

        # a repeat is recognised from state, without fetching again
        runtime.state["files"] = fetched.update["files"]
        again = await researcher.fetch_page.coroutine(hits[0].url, runtime)  # type: ignore[misc]
        assert "already fetched" in reply_text(again)
        assert again.update["fetched"] == [page_id]


class TestVerdictAggregation:
    def test_any_refuted_refutes(self):
        assert combine_verdicts([Verdict.SUPPORTED, Verdict.REFUTED]) == Verdict.REFUTED

    def test_all_supported_supports(self):
        assert combine_verdicts([Verdict.SUPPORTED, Verdict.SUPPORTED]) == Verdict.SUPPORTED

    def test_a_gap_means_not_enough_info(self):
        v = [Verdict.SUPPORTED, Verdict.NOT_ENOUGH_INFO]
        assert combine_verdicts(v) == Verdict.NOT_ENOUGH_INFO

    def test_no_subclaims_is_not_enough_info(self):
        assert combine_verdicts([]) == Verdict.NOT_ENOUGH_INFO

    async def test_subclaim_without_evidence_needs_no_llm(self):
        out = await verify_subclaims(["a", "b"], [[], []])
        assert out.final_verdict == Verdict.NOT_ENOUGH_INFO and out.citations == []


def test_think_tool_acknowledges_without_echoing():
    out = think_tool.invoke({"findings": "FIND", "gaps": "GAP", "next_step": "NEXT"})
    assert out == "Reflection recorded."  # the arguments are already in the context


class _ChatTap(BaseCallbackHandler):
    """Records every message each chat-model call is sent, and every run's inputs."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.inputs: list[str] = []

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        for batch in messages:
            self.calls.append("\n".join(str(m.content) for m in batch))

    def on_chain_start(self, serialized, inputs, **kwargs) -> None:
        self.inputs.append(repr((serialized, inputs, kwargs)))


# A real sentence of the Eiffel Tower article; the scripted model adds one the page lacks.
REAL_SENTENCE = (
    "It is named after the engineer Gustave Eiffel, whose company designed and built "
    "the tower from 1887 to 1889."
)


class ScriptedModel(BaseChatModel):
    """Drives the real graphs: plan two sub-claims, delegate with queries, fetch, extract.

    `retry` makes the orchestrator delegate todo 1 again after the first round: with a
    `focus` ("focus"; re-reads the saved page) or with new `queries` ("queries").
    """

    retry: str = ""
    seen: list[tuple[str, list[str]]] = []
    bound: list[list[str]] = []
    searches: list[str] = []
    fetches: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.bound.append(sorted(getattr(t, "name", str(t)) for t in tools))
        return self

    def with_structured_output(self, schema, **kwargs):
        text = f"{REAL_SENTENCE} ... The tower is made of cheese."
        return RunnableLambda(lambda _: PassageExtraction(passage=text))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = str(messages[0].content)
        is_orch = "coordinate the research phase" in system
        replies = [m for m in messages if isinstance(m, ToolMessage)]
        who = "orch" if is_orch else "reextract" if "already saved" in system else "res"
        self.seen.append((who, [str(m.content) for m in messages]))
        done = ChatResult(generations=[ChatGeneration(message=AIMessage(content="Looks fine."))])
        todos = [
            {"content": "The Eiffel Tower is in Paris.", "status": "pending"},
            {"content": "The Eiffel Tower was built in 1889.", "status": "pending"},
        ]
        queries = [{"query": "Eiffel Tower", "engine": "wikipedia"}]
        if is_orch:
            if not replies:
                calls = [("write_todos", {"todos": todos})]
            elif replies[-1].name == "write_todos":
                calls = [
                    ("delegate", {"todo_id": 1, "queries": queries}),
                    ("delegate", {"todo_id": 2, "queries": queries, "combined": True}),
                    ("delegate", {"todo_id": 9, "queries": queries}),  # unknown id
                ]
            elif self.retry and not any("limit" in str(r.content) for r in replies):
                args: dict[str, Any] = {"todo_id": 1}
                if self.retry == "focus":
                    args["focus"] = "other aspects"
                else:
                    args["queries"] = [{"query": "Eiffel Tower height", "engine": "duckduckgo"}]
                calls = [("delegate", args)]
            else:
                return done
        elif who == "reextract":
            if replies:
                return done
            page_ids = re.findall(r"- (p[0-9a-f]{8}) \|", str(messages[1].content))
            calls = [("extract_passage", {"page_id": i, "focus": "other"}) for i in page_ids]
        elif not replies:
            url = re.search(r"\| (https?://\S+)", str(messages[1].content)).group(1)
            calls = [("fetch_page", {"url": url}), ("fetch_page", {"url": "http://10.0.0.1/x"})]
        elif replies[-1].name == "fetch_page":
            joined = " ".join(str(r.content) for r in replies)
            page_id = re.search(r"page_id=(p[0-9a-f]{8})", joined).group(1)
            calls = [
                ("extract_passage", {"page_id": page_id}),
                ("extract_passage", {"page_id": "../x"}),
            ]
        else:
            return done
        msg = AIMessage(
            content="",
            tool_calls=[
                {"name": n, "args": a, "id": f"c{len(messages)}{i}"}
                for i, (n, a) in enumerate(calls)
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


def scripted(**kwargs: Any) -> ScriptedModel:
    return ScriptedModel(seen=[], bound=[], searches=[], fetches=[], **kwargs)


async def run_scripted(monkeypatch, model: ScriptedModel, **settings: Any):
    # The wiring tests re-run the whole graph several times; the network layer is
    # stubbed so they neither hammer Wikipedia nor flake. TestResearcherTools covers
    # the real fetch.
    async def offline_search(engine: str, query: str, count: int) -> list[SearchHit]:
        model.searches.append(f"{engine}:{query}")
        url = "https://example.org/eiffel"
        return [SearchHit(url=url, title="Eiffel Tower", snippet="", source="wikipedia")]

    class OfflineFetch:
        async def ainvoke(self, args: dict[str, str]) -> FetchedPage:
            model.fetches.append(args["url"])
            text = f"Eiffel Tower\n{REAL_SENTENCE} It stands in Paris."
            return FetchedPage(url=args["url"], title="Eiffel Tower", text=text)

    monkeypatch.setattr(researcher, "_search", offline_search)
    monkeypatch.setattr(researcher, "fetch_url", OfflineFetch())
    for module in (orchestrator, researcher, evidence_retrieval):
        monkeypatch.setattr(module, "get_llm", lambda: model)
    secret = "BRAVE-SENTINEL-KEY"
    monkeypatch.setattr(
        orchestrator,
        "get_settings",
        lambda: Settings(_env_file=None, brave_api_key=secret, **settings),
    )
    tmp = os.path.join(tempfile.gettempdir(), "factcheck-*")
    before = set(glob.glob(tmp))
    tap = _ChatTap()
    events = [
        e
        async for e in orchestrator.research(
            "The Eiffel Tower is in Paris", "auto", {"callbacks": [tap]}
        )
    ]
    assert set(glob.glob(tmp)) == before, "work dir leaked"
    assert not any(secret in blob for blob in tap.inputs), "settings reached a trace input"
    return events


def seen_text(model: ScriptedModel, who: str) -> str:
    return " ".join(" ".join(m) for w, m in model.seen if w == who)


class TestScriptedWiring:
    """Real graphs; the chat model is scripted and the network layer stubbed."""

    async def test_plan_parallel_delegation_and_isolation(self, monkeypatch):
        model = scripted()

        events = await run_scripted(monkeypatch, model)

        kinds = [type(e) for e in events]
        assert kinds.count(PlanCreated) == 1 and kinds[-1] is ResearchDone
        assert kinds.count(PassageFound) == 2
        assert kinds.count(SearchRan) == 2  # run by Python from the orchestrator's queries
        done = events[-1]
        assert isinstance(done, ResearchDone)
        assert done.subclaims == [
            "The Eiffel Tower is in Paris.",
            "The Eiffel Tower was built in 1889.",
        ]
        assert done.combined == [False, True]  # only todo 2 was delegated as combined
        # one passage per todo, and the invented half of the model's answer was dropped
        assert [[p.text for p in ps] for ps in done.passages] == [[REAL_SENTENCE]] * 2

        assert REAL_SENTENCE not in seen_text(model, "orch")
        assert "Unknown todo_id 9" in seen_text(model, "orch")
        assert "2 page(s) saved" not in seen_text(model, "orch")  # one page per todo
        assert "1 page(s) saved for this todo" in seen_text(model, "orch")

        researcher_text = seen_text(model, "res")
        assert "not returned by a search" in researcher_text  # SSRF guard
        assert "Unknown page_id" in researcher_text

        # no model was ever offered a search tool
        assert all("search" not in names for names in model.bound)
        assert ["delegate", "think_tool", "write_todos"] in model.bound
        assert ["extract_passage", "fetch_page"] in model.bound

    async def test_focus_retry_rereads_saved_pages_without_search_or_fetch(self, monkeypatch):
        model = scripted(retry="focus")

        events = await run_scripted(monkeypatch, model, agent_max_retries=1)

        done = events[-1]
        assert isinstance(done, ResearchDone)
        # the retry found the same sentence again: kept once, announced once
        assert [len(ps) for ps in done.passages] == [1, 1]
        assert [type(e) for e in events].count(PassageFound) == 2
        # first attempts only: one search and one fetch per todo, none for the retry
        assert len(model.searches) == 2 and len(model.fetches) == 2
        assert ["extract_passage"] in model.bound
        assert "Focus for this attempt: other aspects" in seen_text(model, "reextract")

    async def test_query_retry_searches_again_and_reuses_the_saved_page(self, monkeypatch):
        model = scripted(retry="queries")

        events = await run_scripted(monkeypatch, model, agent_max_retries=1)

        done = events[-1]
        assert isinstance(done, ResearchDone)
        assert [len(ps) for ps in done.passages] == [1, 1]
        assert len(model.searches) == 3 and "duckduckgo:Eiffel Tower height" in model.searches
        assert len(model.fetches) == 2  # the retry's hit was already saved
        assert "already fetched" in seen_text(model, "res")

    async def test_retry_limit_holds_across_turns(self, monkeypatch):
        model = scripted(retry="focus")

        await run_scripted(monkeypatch, model, agent_max_retries=0)

        assert "limit reached" in seen_text(model, "orch")
        assert "reextract" not in [w for w, _ in model.seen]


@pytest.mark.skipif(not os.getenv("RUN_LLM_TESTS"), reason="set RUN_LLM_TESTS=1 (real LLM calls)")
async def test_agent_run_end_to_end():
    settings = get_settings()
    configured = (settings.llm_provider == "openrouter" and settings.openrouter_api_key) or (
        settings.llm_provider == "ollama" and settings.ollama_model
    )
    if not configured:
        pytest.skip("no LLM configured in server/.env")

    tmp = os.path.join(tempfile.gettempdir(), "factcheck-*")
    before = set(glob.glob(tmp))
    tap = _ChatTap()

    events = [
        e
        async for e in orchestrator.research(
            "The Eiffel Tower is in Paris", "wiki", {"callbacks": [tap]}
        )
    ]

    plans = [e for e in events if isinstance(e, PlanCreated)]
    assert plans and 1 <= len(plans[-1].subclaims) <= settings.agent_max_subclaims
    done = events[-1]
    assert isinstance(done, ResearchDone)
    assert len(done.passages) == len(done.subclaims)

    # context isolation: no passage ever reached an orchestrator turn
    orchestrator_turns = [c for c in tap.calls if "coordinate the research phase" in c]
    assert orchestrator_turns
    for passage in (p for ps in done.passages for p in ps):
        assert not any(passage.text in turn for turn in orchestrator_turns)

    verdict = await verify_subclaims(done.subclaims, done.passages)
    assert verdict.final_verdict in set(Verdict)
    assert set(glob.glob(tmp)) == before, "work dir leaked"
