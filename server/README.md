# server

FastAPI backend for the fact-checking service. Receives a claim, drives a LangGraph pipeline of three LLM agents, and streams progress back to the client as Server-Sent Events while the agents work.

## How it works

### Agent pipeline

```
claim ─▶ DocumentSearchAgent ─▶ EvidenceRetrievalAgent ─▶ ClaimVerificationAgent ─▶ verdict
                                          │
                                          └─ no evidence + retries < 2 ─▶ search again
```

| Agent | What it does |
|---|---|
| **DocumentSearchAgent** | LLM rephrases the claim into 1–3 queries and picks engines (wikipedia / duckduckgo / brave, filtered by which credentials are present and the request's `prefer_source` hint). Python dispatches deterministically. |
| **EvidenceRetrievalAgent** | Concurrent `httpx` + `trafilatura` fetch of every candidate URL. For each page, LLM extracts the 1–3 sentences most relevant to the claim. |
| **ClaimVerificationAgent** | LLM judges entailment per passage (`SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO` + one-sentence reason). Majority vote across passages → final verdict. |

The graph wiring lives in `app/agents/graph.py` (`build_graph()`): a `StateGraph` over `FactCheckState` with a conditional retry edge back to search when no evidence was found and `retries < 2`.

### SSE streaming

`POST /api/v1/verify` returns `text/event-stream`. As the graph runs, `app/api/verify.py` emits named events in order:

`search_started` → `candidates_found` → `passage_found` → `passage_verdict` → `final_verdict` → `done`

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
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override only for a proxy |
| `OLLAMA_HOST` | — | e.g. `http://localhost:11434` (for `ollama`) |
| `OLLAMA_MODEL` | — | Model tag, e.g. `qwen2.5:7b-instruct` |
| `OLLAMA_NUM_CTX` | `8192` | Context window tokens |
| `SEARCH_RESULTS_PER_QUERY` | `3` | Hits per search query |
| `MAX_CONCURRENT_FETCHES` | `3` | Parallel URL fetches |
| `BRAVE_API_KEY` | — | Optional; enables Brave search engine |
| `GOOGLE_CLIENT_ID` | — | From Google Cloud Console OAuth client |
| `GOOGLE_CLIENT_SECRET` | — | From Google Cloud Console OAuth client |
| `JWT_SECRET` | — | Random secret ≥32 chars — `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SESSION_SECRET` | — | Random secret ≥32 chars (separate from JWT_SECRET) |
| `COOKIE_SECURE` | `false` | Set `true` in production (requires HTTPS) |

**Google OAuth setup:** [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Web application), then add `http://localhost:5173/api/v1/auth/google/callback` to **Authorized redirect URIs**.

### Model choice

**OpenRouter.** One model serves all three agents. `evidence_retrieval` makes one call per fetched page, so prefer a cheap, structured-output-capable model. `get_llm()` sends `provider.require_parameters: true`, so requests only route to providers that support `response_format: json_schema`; a model with no such provider returns an error rather than unparsed text. Free (`:free`) models are rate-limited and rarely suit a primary role.

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
│   ├── graph.py           # StateGraph wiring with conditional retry edge
│   ├── document_search.py
│   ├── evidence_retrieval.py
│   └── claim_verification.py
├── tools/                 # @tool-decorated callables: wikipedia_search, duckduckgo_search,
│                          # brave_search, fetch_url (+ tenacity retry)
├── domain/
│   └── state.py           # FactCheckState — internal pipeline state, distinct from API models
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
