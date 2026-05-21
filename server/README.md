# server

FastAPI backend for the fact-checking service. Three LangGraph agents cooperate to verify a claim and stream progress back to the client over SSE.

## Stack

- **FastAPI** + Pydantic v2 (HTTP layer)
- **LangGraph + LangChain** (agent orchestration)
- **Ollama** (local LLM runtime — default `qwen2.5:7b-instruct`)
- **httpx + trafilatura** (concurrent page fetching)
- **SQLModel + aiosqlite** (verification history, async SQLite)
- **uv** (dependency manager)

## Setup & run

```bash
# Ollama must be running first (from repo root)
cd ../infra/compose && docker compose up -d
docker exec -it ollama ollama pull qwen2.5:7b-instruct   # or llama3.1:70b-instruct

# Install deps + configure
uv sync
cp .env.example .env
# Optional: fill in GOOGLE_API_KEY / GOOGLE_CSE_ID / BING_API_KEY
# Wikipedia works without any keys.

# Run
uv run uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Tests

```bash
uv run pytest                              # full suite
uv run pytest tests/test_tools.py -v       # tool integration tests only
```

Per `.claude/rules/microservices.md`, tests hit real external APIs — no mocks. Google/Bing tests skip when no API key is present in `.env`.

## Layout

```
app/
├── main.py                # FastAPI entrypoint; mounts generated routers + binds handlers
├── api/
│   ├── verify.py          # POST /api/v1/verify — drives the graph, yields SSE events
│   ├── history.py         # GET  /api/v1/history — recent verifications + citations
│   └── generated/         # GENERATED — do not edit (regenerate via make -C api generate)
│       ├── models.py
│       └── routers/
├── agents/
│   ├── graph.py           # StateGraph wiring with conditional retry edge
│   ├── document_search.py
│   ├── evidence_retrieval.py
│   └── claim_verification.py
├── tools/                 # @tool-decorated callables (google, bing, wikipedia, fetch_url)
├── domain/
│   └── state.py           # FactCheckState TypedDict — internal pipeline state, not API models
└── platform/
    ├── config.py          # pydantic-settings, loads .env
    ├── llm.py             # cached ChatOllama factory
    ├── streaming.py       # SSE helper
    └── db/                # SQLModel models + async session factory
```

## Agent pipeline

```
claim ─▶ DocumentSearchAgent ─▶ EvidenceRetrievalAgent ─▶ ClaimVerificationAgent ─▶ verdict
                                          │
                                          └─ no evidence + retries < 2 ─▶ search again
```

| Agent | What it does |
|---|---|
| **DocumentSearchAgent** | LLM rephrases the claim into 1–3 queries and picks engines (google / bing / wikipedia, filtered by which credentials are present). Python dispatches deterministically. |
| **EvidenceRetrievalAgent** | Concurrent `httpx` + `trafilatura` fetch of every candidate URL. For each page, LLM extracts the 1–3 sentences most relevant to the claim. |
| **ClaimVerificationAgent** | LLM judges entailment per passage (`SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO` + one-sentence reason). Majority vote across passages → final verdict. |

## SSE event taxonomy

Events emitted by `app/api/verify.py` in order:

`search_started` → `candidates_found` → `retrieval_started` → `passage_found` → `passage_verdict` → `final_verdict` → `done`

On any error: `error` (uniform shape; clients never handle two failure modes).

## Endpoint binding quirk

`app/main.py` mounts each generated router stub, then **removes** the route and re-registers it with the real handler under the same path/method/response_model. Mutating `route.endpoint` in-place doesn't work because `APIRoute.__init__` captures `is_async_callable(endpoint)` once at construction — an in-place swap silently calls async handlers as if they were sync.

## Regenerating the API contract

```bash
# From repo root:
make -C api generate   # rewrites app/api/generated/ + web-client/src/api.ts
make -C api check      # CI gate — fails if generated code drifted
```

Edit `api/openapi.yaml`, run `generate`, commit both together.
