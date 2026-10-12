# Deep-agent redesign: decisions and reasons

Branch: `feat/autonomous-agent`. Status: **implemented**.

## Goal

Move from the fixed `search → retrieve → verify` LangGraph pipeline to an autonomous
"deep agent": an orchestrator with a todo list that delegates research to subagents
(so raw web content never enters its context), stores raw fetched pages in files, and
uses a `think_tool` for structured reflection (findings, gaps, next steps).

## Decisions

### D1. Autonomy covers research only; verification stays a separate step

The orchestrator loops (plan → delegate → reflect) until it judges the evidence
sufficient. The existing `claim_verification_agent` then labels each passage and
produces the verdict and citations.

Why:

- Keeps `passage_verdict` / `final_verdict` and history/citation persistence unchanged.
- Judging stays deterministic and testable instead of a free-form agent turn. Letting
  the orchestrator judge would put passages back into its context, which is exactly
  the pollution the subagents exist to avoid.
- Research is where the fixed pipeline is weakest: one-shot queries, and a retry that
  only fires on zero evidence.

Accepted trade-off: the orchestrator never sees per-passage labels, so `think_tool`
reflects on coverage and gaps, not on verdict conflict. Revisit (run the verifier
inside the loop) if conflicting evidence turns out to be the common failure.

### D2. Todo items are sub-claims, not research tasks

The orchestrator decomposes the claim into atomic assertions. A simple claim yields exactly one todo (same behaviour as today). Each sub-claim is researched and verified separately; the overall verdict is aggregated: all SUPPORTED → SUPPORTED, any REFUTED → REFUTED, otherwise NOT_ENOUGH_INFO.

Why: compound claims are where the current pipeline fails (one blended verdict lets evidence for half the claim mask the other half), and with research tasks as todos the
list would be narration while `think_tool` does the real planning.

Consequence: `claim_verification_agent` runs once per sub-claim.

### D3. Hand-roll on the current stack; do not adopt `deepagents`

`deepagents` 0.7.23 requires `langchain>=1.4.3` and `langchain-core>=1.6.7`; this
project pins `langgraph<0.3`, `langchain<0.4`, `langchain-core<0.4`
(`server/pyproject.toml`). Adopting it is a LangChain 1.x migration that would touch
`get_llm()`, structured output and the tracing code, and would bury this branch under
a framework upgrade.

Instead: `create_react_agent` for the orchestrator and the subagent, with our own
`write_todos`, `think_tool` and `delegate` tools. The tool contracts match
`deepagents`', so a later migration is mechanical.

**Update:** the stack was then moved to LangChain/LangGraph 1.x (`langchain` 1.4.4, `langgraph` 1.2.14, `langchain-core` 1.6.9, `langchain-openai`/`-ollama` 1.x) and both agents now use `langchain.agents.create_agent` (`prompt=` became `system_prompt=`) because `langgraph.prebuilt.create_react_agent` is deprecated. 

This also removes the version conflict above, so `deepagents` is installable now; we still hand-roll because our `Run`-closure tools and bounds are the part that matters here.
`langchain-community` was dropped: nothing imported it.

### D4. Per-run context object instead of graph-state tool updates

> **Superseded** by "Second pass: LangChain 1.x idioms" below. The closure design was a workaround for the pinned LangGraph 0.2; kept here for the history.

Tools are built by a factory that closes over a per-request `RunContext` (todos,
collected passages, work dir). Tools write there; the SSE layer reads it.

Why: on the pinned langgraph, tools cannot cleanly update graph state; a closure is
the smallest thing that works and keeps passages out of message history by
construction (see D7).

### D5. Subagent per sub-claim, run concurrently

`delegate(subclaim_id)` spawns a research subagent with only that sub-claim in its
context and the search/fetch/extract tools. Subagents share the existing
`MAX_CONCURRENT_FETCHES` semaphore. Engine selection is Python filtering of its tool
list by `prefer_source` and available credentials (Brave only with `BRAVE_API_KEY`),
so `DocumentSearchAgent` is deleted.

### D6. Raw pages go to a per-run temp dir, deleted when the run ends

The researcher's `fetch_page` writes the page to a file and returns only a `page_id`, title and size. `extract_passage(page_id)` reads the file and runs the existing `PASSAGE_PROMPT` extraction. 

Work dir is a `TemporaryDirectory` scoped to the request.

The model passes an opaque `page_id`, never a path, so it cannot read arbitrary files.

Why: no cross-request state (the service must stay stateless per `.claude/rules/microservices.md`), nothing to garbage-collect, and pages never need to outlive the run because only the extracted passage is a citation.

### D7. Subagent returns passages out-of-band; the orchestrator sees only summaries

Extracted `Passage`s are appended to the `Run` by the extract tool. The researcher sees its own passages (its context is isolated and discarded), but the orchestrator's view of a delegation is `N passage(s) extracted from: <urls>` plus the researcher's short summary.

**Why**: page text never enters any LLM message history except the extraction call, and passage text never enters the orchestrator's. That makes the context-isolation goal and the tracing goal (next item) the same mechanism.

### D8. Tracing scrub stays as is

Because of D6/D7, raw page text is only ever in the extraction prompt, which the
existing `ARTICLE_HEADER` cut in `app/platform/tracing.py` already handles.

No new scrubbing code. `test_tracing.py` gets one added case: a full agent run's messages contain no page text.

### D9. Hard bounds, configurable, defaults to tune after first runs

New settings with defaults: max sub-claims 5; max delegations per sub-claim 3
(replaces `MAX_RETRIES=2`, which allowed 3 searches); max orchestrator turns 12; max tool calls per subagent 8; run wall-clock timeout 120 s. Plus LangGraph's
`recursion_limit` as a backstop. 
When a bound trips, the run proceeds to verification with what it has rather than failing.

Why: an autonomous loop on a paid OpenRouter model needs a ceiling, and "verify what we have" degrades to NOT_ENOUGH_INFO instead of an error.

### D10. UI shows the plan via one new SSE event; per-sub-claim ids deferred

Add `plan_created` to `api/openapi.yaml` with payload `{subclaims: string[]}`; regenerate both ends; render the list in `AgentTimeline.tsx`. Existing `passage_*` and `final_verdict` events are unchanged. (The generated `_EnsureEveryEventCovered` guard forces the frontend to handle any new event, so it cannot be backend-only.)

**Why**: the todo list is the most legible thing a deep agent produces. Sub-claim ids on `passage_*` events and per-sub-claim verdicts in the UI are skipped: more spec surface for a display nicety. Add when the UI needs to group evidence by sub-claim.

## Findings and risks

- **Tool-calling reliability on small models.** This project previously found
  `function_calling` structured output returns `None` on small Ollama models (hence `method="json_schema"`). A ReAct loop needs real tool calling. Target OpenRouter models that support tools; Ollama is best-effort and may need a bigger model.
- **Nondeterminism and cost.** Multiple LLM turns per sub-claim. D9 bounds it; log
  turn and tool-call counts so cost per run is observable in LangSmith.
- **Latency.** Sub-claims run concurrently, but the orchestrator loop is serial. Expect
  slower runs than the fixed pipeline for simple claims; consider a fast path (one
  todo, one delegation, no reflection) if that regresses UX.
- **Replace, don't flag.** The new graph replaces `build_graph()`; git history is the
  rollback. `evidence_retrieval` extraction and `claim_verification_agent` are reused.

## Tests

Project rule: integration tests hit real APIs. Agent behaviour is nondeterministic, so
assert structure, not exact verdicts: a plan was created; a one-assertion claim yields
one todo; no orchestrator message contains fetched page text; the verdict is in the
enum; bounds trip cleanly (set max delegations to 1 and check the run still ends in a
verdict). Tests needing an LLM key skip without one.

## Implementation order

1. `RunContext` + file-backed `fetch_url` + `extract_passage` tools (testable alone).
2. Research subagent and `delegate`.
3. Orchestrator with `write_todos` and `think_tool`; new `build_graph()`; bounds.
4. Wire `verify.py`: stream plan and passages from `RunContext`, aggregate verdicts.
5. Spec: `plan_created`; regenerate; frontend timeline.
6. Docs: CLAUDE.md architecture table, server README pipeline section.

## As built

Differences from the plan, and what the first live run showed.

- **SSRF guard (not in the original design).** Once the model chooses what to fetch, a prompt-injected page could point it at internal addresses. `fetch_page` therefore accepts only URLs a `search` call returned (`Run.seen_urls`), same trust level as the old pipeline.
- **`write_todos` is single-shot.** A second call is rejected; a repeat attempt is a
  `delegate` with a `focus`. Simpler than plan revision, and enough so far.
- **Safety nets.** If the orchestrator never plans, the claim becomes the single todo
  and one researcher runs on it. A timeout or turn limit still emits `ResearchDone`
  so verification runs. Real LLM/provider errors are not swallowed: they surface as
  the SSE `error` event.
- **Reducer change.** The web client now accumulates `queries` and `candidates`
  (deduplicated by URL) instead of replacing them, because the agent searches many times per run.
- **Removed:** `graph.py`, `document_search.py`, `retries`/`SearchOutput` in the
  domain state, and `MAX_RETRIES`.

### First live run (OpenRouter free model, Marie Curie Physics + Chemistry claim)

- Planned 2 sub-claims, researched in parallel, 2 supporting Wikipedia passages,
  verdict SUPPORTED. Correct, but **84 s** and about 25+ LLM calls, versus roughly a dozen calls before.
- The researcher kept searching for contradicting sources after it already held an authoritative passage. The prompt was tightened ("stop once a source clearly settles it"); the re-run could not be measured because the free tier's 50 requests/day were spent. **Re-measure latency and call count with a paid model before judging D1/D9.**
- Practical consequence: on a free OpenRouter model, one run uses roughly half the daily quota.

### Verification done

- Real Wikipedia/DuckDuckGo tool tests plus bounds and guard tests: `tests/test_agents.py`.
- Opt-in end-to-end test (`RUN_LLM_TESTS=1`) asserts a plan exists, no passage text appears in any orchestrator turn, the verdict is valid, and no temp dir leaks.
- A scripted tool-calling model driving the real loop confirmed: parallel delegation, unknown-id and SSRF/path-traversal refusals, researcher runs nested under the `fact-check` trace via the passed callbacks, temp dir removed, and the SSE order
`plan_created → search_started → candidates_found → passage_found →
passage_verdict → final_verdict → done` with the history row persisted.

## Second pass: LangChain 1.x idioms

The first build kept 0.2-era workarounds after the stack moved to 1.x (only
`create_react_agent` was renamed). This pass makes the agents idiomatic. The _logic_ (plan, delegate, researcher loop, verification) is unchanged; the retry design is
deliberately deferred.

| Before                                               | Now                                                                                                                                 | Why                                                                                                                         |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `StructuredTool.from_function` closures over a `Run` | module-level `@tool(parse_docstring=True)`; per-argument descriptions reach the model                                               | closures were only needed because 0.2 tools could not touch state                                                           |
| `Run` object (plan, passages, pages, queue)          | `Ctx` (frozen context) + `ResearchState` / `ResearcherState` (graph state)                                                          | tools update state by returning `Command`; `runtime.state`, `.context`, `.stream_writer`, `.tool_call_id` via `ToolRuntime` |
| hand-written `write_todos`                           | `TodoListMiddleware` with our own short prompts; plan lives in `state["todos"]`                                                     | stock prompts push step-by-step status updates, which only add LLM turns                                                    |
| `recursion_limit` arithmetic + `GraphRecursionError` | `ModelCallLimitMiddleware` (orchestrator), `ToolCallLimitMiddleware` (researcher); a generous `recursion_limit` stays as a backstop | graceful end instead of an exception                                                                                        |
| `asyncio.Queue` + producer task                      | `stream_mode=["custom","values"]`; tools emit events through `runtime.stream_writer`, `delegate` forwards the researcher's          | one mechanism; the deadline wraps each `anext` so it never fires inside the consumer                                        |
| `p1`, `p2` page ids                                  | `p` + 8 hex of sha1(url)                                                                                                            | parallel researchers write the same state keys; per-run counters would collide                                              |

### Decisions

- **Pages stay on disk; state holds `FileRef(url, title, path)`.** Option 1 of the
  two considered. LangSmith records graph state at every step, so putting article
  text in state would break "never upload raw page text" unless a scrub filtered it;
  with refs the guarantee holds by construction. The temp dir stays.
- **Context carries `Settings` and is not traced.** Checked: a sentinel
  `brave_api_key` in the context never appears in callback inputs
  (`tests/test_agents.py::run_scripted`).
- **Reducers.** Parallel `delegate` calls write `files`, `passages`, `delegations` in
  the same step, so these keys merge (`dict |`, per-todo list concat, counter add);
  without them LangGraph raises `InvalidUpdateError`.
- **`ResearchDone` is built from the event stream, not from final state.** State is
  only updated when a tool step completes, so a timeout would lose in-flight passages;
  events arrive as they are found, which keeps "verify what we have".
- **Delegation count lives in state.** Two `delegate(1)` calls in the same turn both
  see the old count and can overshoot the limit by one. Accepted: the model-call limit
  bounds the run anyway.
- **Re-planning.** The prompt forbids a second `write_todos`, but the stock tool does
  not. A re-plan that reorders todos would mislabel per-todo passages. Accepted until
  it is seen in practice; the UI shows the latest plan.
- **Verbatim guard.** `extract_passage_text` now drops any part of the model's answer
  that is not a substring of the page (after whitespace, quote and dash
  normalisation). A citation can no longer contain text the page lacks.
- **`extract_passage(page_id, focus, part)`.** Superseded by the third pass below
  (`part` is gone; the excerpt is ranked instead).

## Third pass: retry by re-extraction

The logic pass. Decisions, in the order they were settled:

- **The orchestrator writes the queries and picks the engine per query**
  (`delegate(todo_id, queries=[{query, engine}], focus)`). Python runs them in
  parallel (`researcher.run_queries`) before the researcher starts, with the
  engine fallback (originally brave→duckduckgo on a 429; see "Fourth pass" for what it
  is now). So `search` is no longer a model tool: with the
  arguments fixed by the orchestrator it would only cost a relay turn, and a researcher
  could ignore the orchestrator's queries. An engine that is not available for the
  request is replaced by the first one that is. Zero hits ends the attempt without an
  LLM call.
- **A retry is either new queries or a focus, never an automatic ladder.**
  - `queries` given: search, fetch, extract. New pages join the saved set.
  - No `queries`, pages saved, `focus` given: no search, no fetch; the researcher gets
    only `extract_passage` and re-reads the saved pages with the new focus. This is
    cheap because raw pages are on disk, and it is adaptive because of the next point.
  - No `queries` on the first attempt, nothing saved, or no focus on a re-extract:
    rejected with a message; the rejection does not use an attempt.
- **Ranked excerpt instead of first-10k.** `best_excerpt` scores each line of the saved
  page by IDF-weighted word overlap with claim + focus (no model call) and keeps the
  best lines up to 10 000 chars in page order, always including the lead. A page that
  fits goes through whole. Cost per extraction is flat (~2.5k tokens) however long the
  page, facts deep in an article are reachable, and a new focus selects different lines,
  which is what makes a re-extract more than a re-roll. Rejected: whole page (cost grows
  with the page and with every retry, small models overflow) and chunk-per-call (same
  tokens, several requests: the free tier counts requests).
- **No verdict trigger.** The orchestrator decides from the researcher's summary, which
  starts with a code-generated line (passages extracted, pages saved). It once also
  ended with the model's `STATUS: settled|partial|none`, but that self-grade said
  "settled" from model memory with no source, so it was dropped: the orchestrator
  weighs the passage counts in `think_tool` before any retry or finish (a prompt rule,
  not enforced in code). Verification stays after the loop, so research remains the
  only autonomous part.
- **Retry is optional.** `AGENT_MAX_RETRIES` (default 2; replaces
  `AGENT_MAX_DELEGATIONS`, same cap of three runs) is a ceiling. The prompt says to stop
  on `settled` or when the only call it could write repeats an earlier one; a thin
  result ends as NOT_ENOUGH_INFO instead of being forced to a side.
- **Passages are de-duplicated** by (todo, url, normalised text) where `research()`
  collects events, before they are streamed or judged. Without this a repeat (a focus
  retry that finds the same sentence, or two same-turn delegates) would be judged and
  counted twice in the majority vote.
- **Not done.** No guard against two same-turn delegates for one todo (the overshoot is
  one extra run, and dedup keeps it from changing a verdict); no check that a retry's
  arguments differ from earlier ones (prompt only); the prompts are first drafts.
- **Not verified with a real model.** Wiring is covered by scripted-model tests
  (`tests/test_agents.py::TestScriptedWiring`); how well a model picks queries, engines
  and retries, and the call count / latency, still need a run on a real model.
- **Fetch guard.** The `seen_urls` allowlist only stops the model being talked into a
  URL; it does not cover a search hit that redirects inward or a public name that
  resolves to a private address. `fetch_url` therefore resolves the host, requires every
  address to be globally routable, and follows redirects by hand so each hop is checked
  (`tests/test_fetch_guard.py`, no network). Residual: resolve-then-connect is not
  atomic, so a rebinding record can still slip through; an egress NetworkPolicy would
  close it.

## Fourth pass: review fixes

From a review of the retry logic and the prompts. What changed and why:

- **A failed search is not "no results".** `_search` raises; `run_queries` retries once on
  `SEARCH_FALLBACK` (brave, wikipedia → duckduckgo) when the request allows it, and a
  query that fails everywhere is reported as `Search failed … Try another engine`, so the
  orchestrator changes engine instead of rewording. Wikipedia's wrapper returns `{}` on a
  429 page, so an answer with no `query` key now raises.
- **Engine swap keeps the kind.** An engine the request does not allow is replaced by an
  allowed one of the same kind (web vs. encyclopedia), not by `engines[0]`.
- **The summary lists the saved pages** (title, URL, passage or not; titles flattened and
  cut at 80 chars) so the orchestrator can tell "wrong pages" (new queries) from "right
  pages, missed passage" (focus).
- **tenacity retries only network errors and 5xx** (`is_transient`). A 403/404/429 fails
  fast: a retry answers the same and brave already has a fallback.
- **A focus retry re-reads at most the 4 most recent pages** (`REEXTRACT_MAX_PAGES`), so it
  fits the tool-call limit. The orchestrator is told.
- **`delegate` no longer swallows every exception.** Provider errors propagate as the SSE
  `error` event, as the "As built" section always claimed. (The first version also
  caught `OSError`/`httpx.HTTPError` around the researcher run; see "Fifth pass".)
- **`think_tool` is the orchestrator's only.** Researchers cannot act on a gap (the fetch
  cap is fixed), so it cost a model call and a tool slot for nothing. It returns an ack,
  not an echo of its arguments.
- **Prompts.** write_todos is called alone and delegation follows in the next turn
  (parallel tool calls share one state snapshot, so a same-turn `delegate` saw no plan);
  queries per delegate are 3 everywhere and extras are reported, not dropped silently;
  extraction picks contradicting sentences as readily as supporting ones and treats the
  article as untrusted; the orchestrator treats summaries as data; the extraction header is
  `Article (excerpt):` (and `ARTICLE_HEADER` in `tracing.py` with it).
- **Dead prompt text removed.** Search and fetch tool docstrings are not read by any model.

Not changed, on purpose: the researcher still grades its own `STATUS`.

## Fifth pass: review follow-ups

- **Provider errors are never "no passage".** `extract_passage_text` caught every
  exception and returned `None`, so a dead quota during extraction ended as
  `STATUS: none` and a silent NOT_ENOUGH_INFO. It now returns `None` only when the model
  answered unusably (`ValueError`, which covers `OutputParserException` and
  `ValidationError`; `TypeError`; the OpenAI length/content-filter finish errors).
  Anything else propagates to the SSE `error` event.
- **No broad `except` around the researcher's model calls.** `except (OSError,
httpx.HTTPError)` also matched the model client's own connection failures (Ollama
  surfaces an unreachable server that way), turning an outage into per-todo
  `STATUS: partial`. The one real tool-side case, a saved page that cannot be read, is
  handled at the tool boundary: `extract_passage` returns an error string and the
  attempt carries on.
- **The orchestrator prompt formats `REEXTRACT_MAX_PAGES` in** instead of repeating "4".
- **Wikipedia gets one retry on a network blip** (`OSError`: requests' `ConnectionError`
  and `Timeout`), not on an empty or error answer: a 429 page answers the same again and
  the fallback is the remedy. With `prefer_source="wiki"` there is no fallback, so the
  retry is all that protects a single query.

Still open: "at most 3 pages" is prompt-only (the tool-call limit allows more fetches);
`AGENT_MAX_PAGES` would make it hard.
