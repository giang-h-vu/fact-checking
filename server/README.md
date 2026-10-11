# server

FastAPI backend for the fact-checking service. Receives a claim, drives a LangGraph pipeline of three LLM agents, and streams progress back to the client as Server-Sent Events while the agents work.

## How it works

### Agent pipeline

```
claim ─▶ Orchestrator ── write_todos ─▶ [sub-claim 1..n]
              │ delegate (parallel)
              ▼
        Researcher subagents ─▶ passages          (raw pages stay in per-run files)
              │ think_tool / retry on gaps
              ▼
        ClaimVerificationAgent per sub-claim ─▶ combined verdict
```

| Part | What it does |
|---|---|
| **Orchestrator** (`orchestrator.py`) | Tool-calling loop. `write_todos` splits the claim into atomic sub-claims (one for a simple claim), `delegate` runs a researcher per sub-claim (parallel when emitted in one turn), `think_tool` reflects on the summaries. Never sees page or passage text. |
| **Researcher** (`researcher.py`) | One per sub-claim, own context. Python runs the orchestrator's `{query, engine}` list over the engines allowed by `prefer_source` and credentials (with fallback, and failures reported as failures); the model gets `fetch_page(url)` (writes the page to a file; only URLs a search returned) and `extract_passage(page_id, focus)` (LLM picks the relevant sentences). Returns a short summary that lists the saved pages. |
| **ClaimVerificationAgent** | LLM judges entailment per passage (`SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO` + one-sentence reason); majority vote per sub-claim. Overall: any REFUTED refutes, all SUPPORTED supports, else NOT_ENOUGH_INFO. |

Autonomy covers research only; judging stays a separate deterministic step. Design decisions and their reasons are in `../docs/deep-agent-design.md`. Tool calls need a model that supports tool calling (OpenRouter models listing `tools`; small Ollama models are unreliable at it).

**Bounds** (`AGENT_*`, see Configuration): when any trips the run verifies what it has collected instead of failing. Each run makes tens of LLM calls (orchestrator turns, researcher turns, one extraction per page, one judgement per passage), so a free-tier OpenRouter daily quota covers only a few runs.

### SSE streaming

`POST /api/v1/verify` returns `text/event-stream`. As the graph runs, `app/api/verify.py` emits named events in order:

`plan_created` → (`search_started` → `candidates_found` → `passage_found`)\* → `passage_verdict` → `final_verdict` → `done`

On any failure: a single `error` event.

Because OpenAPI can't bind an SSE event *name* to a payload schema, `verify.py` enforces the pairing itself:

- `EVENT_PAYLOAD: dict[SseEventType, type[BaseModel] | None]` — single source of truth for which generated payload belongs to which event.
- `@overload` signatures on the `sse()` helper pin each event to its payload at type-check time.
- `sse()` serialises with `model_dump(mode="json")` — required because the generated `Verdict` is a plain `Enum`; a naive `str()` would emit `"Verdict.SUPPORTED"` instead of `"SUPPORTED"`.
- `tests/test_api.py::TestSsePayloads` asserts the registry covers every `SseEventType`.

### Auth

Google OAuth 2.0 (`app/api/auth.py` + `app/platform/auth/`): the OAuth dance produces a JWT stored in an HTTP-only cookie; protected routes resolve the user via a FastAPI dependency. Final verdicts and citations are persisted per user to SQLite (`app/platform/db/`).

## Stack

- **FastAPI** + Pydantic v2 (HTTP layer) + **sse-starlette** (streaming)
- **LangGraph + LangChain** (agent orchestration)
- **OpenRouter** (hosted LLM API, default) or **Ollama** (local runtime, `qwen2.5:7b-instruct`) — chosen by `LLM_PROVIDER`
- **httpx + trafilatura** (concurrent page fetching)
- **SQLModel + aiosqlite** (verification history, async SQLite)
- **uv** (dependency manager)

## Setup & run

```bash
# Install deps + configure
uv sync
cp .env.example .env
# Fill in Google OAuth credentials + JWT/session secrets, then pick an LLM backend:
#   LLM_PROVIDER=openrouter  + OPENROUTER_API_KEY + OPENROUTER_MODEL
#   LLM_PROVIDER=ollama      + OLLAMA_HOST + OLLAMA_MODEL (see below)

# Ollama only: start it first (from repo root) and pull the model
docker compose --profile ollama up -d ollama
docker exec -it ollama ollama pull qwen2.5:7b-instruct   # or llama3.1:70b-instruct

# Run
uv run uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Configuration

All settings load from `.env` via pydantic-settings (`app/platform/config.py`):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `openrouter` (hosted) or `ollama` (local) |
| `OPENROUTER_API_KEY` | — | Required for `openrouter`. [openrouter.ai/keys](https://openrouter.ai/keys) — paid models need credits |
| `OPENROUTER_MODEL` | — | Model slug, e.g. `anthropic/claude-haiku-4.5` |
| `OPENROUTER_FALLBACK_MODELS` | — | Optional comma-separated slugs tried in order if the primary errors (e.g. `:free` models that list structured-output support) |
| `OPENROUTER_REQUESTS_PER_MINUTE` | `18` | Client-side cap on model calls (OpenRouter allows free models and new accounts 20/min); `0` = off |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override only for a proxy |
| `OLLAMA_HOST` | — | e.g. `http://localhost:11434` (for `ollama`) |
| `OLLAMA_MODEL` | — | Model tag, e.g. `qwen2.5:7b-instruct` |
| `OLLAMA_NUM_CTX` | `8192` | Context window tokens |
| `SEARCH_RESULTS_PER_QUERY` | `3` | Hits per search query |
| `MAX_CONCURRENT_FETCHES` | `3` | Parallel URL fetches |
| `BRAVE_API_KEY` | — | Optional; enables Brave search engine |
| `AGENT_MAX_SUBCLAIMS` | `5` | Max sub-claims the orchestrator may plan |
| `AGENT_MAX_RETRIES` | `2` | Extra research attempts per sub-claim after the first (new queries, or a re-read of the saved pages with a new focus) |
| `AGENT_MAX_TURNS` | `12` | Orchestrator LLM turns |
| `AGENT_MAX_TOOL_CALLS` | `8` | Tool calls per researcher subagent |
| `AGENT_TIMEOUT_SECONDS` | `120` | Wall-clock cap on the research phase |
| `LANGSMITH_TRACING` | `false` | Send run traces to LangSmith; raw page text is scrubbed, only extracted passages are kept. Forced off in tests |
| `LANGSMITH_API_KEY` | — | Required when tracing is on |
| `LANGSMITH_PROJECT` | `fact-checking` | LangSmith project to file traces under |
| `LANGSMITH_ENDPOINT` | — | Only for EU workspaces: `https://eu.api.smith.langchain.com` |
| `GOOGLE_CLIENT_ID` | — | From Google Cloud Console OAuth client |
| `GOOGLE_CLIENT_SECRET` | — | From Google Cloud Console OAuth client |
| `JWT_SECRET` | — | Random secret ≥32 chars — `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SESSION_SECRET` | — | Random secret ≥32 chars (separate from JWT_SECRET) |
| `COOKIE_SECURE` | `false` | Set `true` in production (requires HTTPS) |

**Google OAuth setup:** [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Web application), then add `http://localhost:5173/api/v1/auth/google/callback` to **Authorized redirect URIs**.

### Model choice

**OpenRouter.** One model serves the orchestrator, researchers, extraction and judging. Pick one that supports both tool calling and structured output, and is cheap: extraction makes one call per fetched page. `get_llm()` sends `provider.require_parameters: true`, so requests only route to providers that support `response_format: json_schema`; a model with no such provider returns an error rather than unparsed text. Free (`:free`) models are rate-limited and rarely suit a primary role.

**Ollama.**

| Model | VRAM | Notes |
|---|---|---|
| `llama3.1:70b-instruct` | ~48 GB | Best quality |
| `qwen2.5:7b-instruct` | ~8 GB | Good enough for development |

`get_llm()` is cached: restart the server after changing any LLM setting.

## Tests

```bash
uv run pytest                              # full suite
uv run pytest tests/test_tools.py -v       # tool integration tests only
RUN_LLM_TESTS=1 uv run pytest tests/test_agents.py   # + real-LLM agent run (~30 LLM calls)
```

Per `.claude/rules/microservices.md`, tests hit real external APIs — no mocks. Tests needing missing credentials skip.

## Layout

```
app/
├── main.py                # create_app() — CORS + include_router() for the hand-written routers
├── api/
│   ├── auth.py            # Google OAuth login/callback/logout/me
│   ├── verify.py          # POST /api/v1/verify — drives the graph, yields SSE events
│   ├── history.py         # GET  /api/v1/history — recent verifications + citations
│   └── generated/
│       └── models.py      # GENERATED Pydantic models — do not edit (make -C api generate)
├── agents/
│   ├── orchestrator.py    # research(): todo planning + delegate loop, bounds, temp dir
│   ├── researcher.py      # subagent: run_queries / fetch_page / extract_passage
│   ├── run.py             # Ctx, graph state + reducers, Event types
│   ├── evidence_retrieval.py   # passage extraction from one page
│   └── claim_verification.py
├── tools/                 # @tool-decorated callables: wikipedia_search, duckduckgo_search,
│                          # brave_search, fetch_url (+ tenacity retry)
├── domain/
│   └── state.py           # FactCheckState — one claim + evidence + verdict, distinct from API models
└── platform/
    ├── config.py          # pydantic-settings, loads .env
    ├── llm.py             # get_llm(): ChatOpenAI (OpenRouter) or ChatOllama, per LLM_PROVIDER
    ├── auth/              # OAuth client, JWT tokens, cookies, route dependencies
    └── db/                # SQLModel models + async session factory
```

Routers are hand-written; only the **models** are generated. The API models (`app/api/generated/`) and the internal pipeline state (`app/domain/state.py`) are deliberately separate — the pipeline can evolve without breaking the public contract.

## Regenerating the API contract

```bash
# From repo root:
make -C api generate   # rewrites app/api/generated/models.py + web-client/src/api.ts
make -C api check      # CI gate — fails if generated code drifted
```

Edit `api/openapi.yaml`, run `generate`, commit both together.
