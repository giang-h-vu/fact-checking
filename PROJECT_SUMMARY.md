# Project summary — Fact-Checker on FastAPI + LangGraph + OpenRouter / Ollama

## What the system does

A user submits a natural-language claim; three async LangGraph agents cooperate to produce a verdict (`SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO`) with citations. Progress streams to the UI over Server-Sent Events as the agents work.

```
claim ─▶ DocumentSearchAgent ─▶ EvidenceRetrievalAgent ─▶ ClaimVerificationAgent ─▶ verdict
                                          │
                                          └─ no evidence + retries < 2 ─▶ search again
```

---

## Repo layout

```
fact-checking/
├── api/                              # SHARED CONTRACT — spec + codegen tooling
│   ├── openapi.yaml                  # single source of truth (only thing humans edit here)
│   ├── Makefile                      # make {generate,lint,check}
│   └── scripts/                      # codegen.sh, package.json, redocly.yaml
│
├── server/                           # FastAPI · LangGraph · OpenRouter or Ollama (Python, uv)
│   ├── pyproject.toml
│   ├── .env.example
│   └── app/
│       ├── main.py                   # create_app() — includes hand-written routers
│       ├── api/                      # HTTP layer (hand-written routers)
│       │   ├── verify.py             #   POST /api/v1/verify → SSE stream (auth required)
│       │   ├── history.py            #   GET  /api/v1/history → JSON (auth required, per-user)
│       │   ├── auth.py               #   Google OAuth login/callback/refresh/logout/me
│       │   └── generated/
│       │       └── models.py         #   GENERATED Pydantic v2 models — do not edit
│       ├── agents/                   # LangGraph nodes (all async)
│       │   ├── graph.py              #   StateGraph with conditional retry edge
│       │   ├── document_search.py    #   LLM plans queries; asyncio.gather dispatches
│       │   ├── evidence_retrieval.py #   concurrent httpx fetch + LLM passage extraction
│       │   └── claim_verification.py #   LLM entailment judge per passage; majority vote
│       ├── tools/                    # LangChain @tool callables (async)
│       │   ├── wikipedia_search.py   #   MediaWiki opensearch (always available)
│       │   ├── duckduckgo_search.py  #   DuckDuckGo (always available; no API key)
│       │   ├── brave_search.py       #   Brave Search (BRAVE_API_KEY required)
│       │   ├── fetch_url.py          #   httpx + trafilatura page fetch
│       │   └── sources.py            #   SearchHit, SearchSource types
│       ├── domain/
│       │   └── state.py              #   FactCheckState, Citation, PassageVerdict, Verdict
│       └── platform/                 # cross-cutting infrastructure
│           ├── config.py             #   pydantic-settings (Settings, get_settings())
│           ├── llm.py                #   get_llm(): ChatOpenAI→OpenRouter or ChatOllama, per LLM_PROVIDER
│           ├── db/                   #   SQLModel + async SQLite
│           └── auth/                 #   Google OAuth + JWT session management
│               ├── oauth.py          #     Authlib Google OIDC client (lru_cached)
│               ├── tokens.py         #     mint/decode access JWT; hash refresh token
│               ├── cookies.py        #     set_auth_cookies / clear_auth_cookies
│               └── dependencies.py   #     get_current_user FastAPI dependency
│
├── web-client/                       # React 18 · Redux Toolkit · MUI v5 · Vite · TypeScript
│   └── src/
│       ├── api.ts                    # GENERATED TS types (openapi-typescript)
│       ├── lib/client.ts             # openapi-fetch client (parseAs: "stream" for SSE)
│       ├── components/
│       │   ├── AgentTimeline.tsx     # live progress (queries → sources → verdicts)
│       │   ├── SearchInput.tsx       # claim input + prefer_source toggle
│       │   ├── Dashboard.tsx
│       │   ├── VerdictChip.tsx
│       │   └── StyledWrappers.ts     # shared MUI styled components
│       ├── pages/
│       │   ├── Home.tsx              # search + live AgentTimeline + final verdict
│       │   ├── History.tsx           # GET /api/v1/history — past verifications
│       │   ├── Login.tsx             # Google sign-in screen (public route)
│       │   ├── Login.styles.ts       # styled components + keyframes for Login
│       │   └── HowItWorks.tsx        # static explainer page
│       ├── store/
│       │   ├── actions/
│       │   │   ├── factcheckActions.ts  # fetch + ReadableStream → dispatch per SSE event
│       │   │   └── authActions.ts       # fetchMe, logout thunks
│       │   └── reducers/
│       │       ├── factcheckReducer.ts  # accumulates progress; sets verdict on final_verdict
│       │       ├── authReducer.ts       # {user, status: loading|authenticated|unauthenticated}
│       │       └── rootReducer.ts       # combineReducers
│       └── types/
│           ├── api.ts                # re-exports aliases from generated api.ts (incl. User)
│           ├── sse.ts                # SsePayloadMap + compile-time coverage guard
│           └── domain.ts             # Passage/PassageVerdict aliases
│
├── docker-compose.yaml               # full-stack: server + web (nginx); Ollama only with --profile ollama
├── .github/workflows/                # ci · test-tools · deploy · bootstrap
└── infra/
    ├── terraform/                    # AKS cluster, subscription budget, GitHub OIDC identity
    ├── k8s/bootstrap/                # set-once: namespace, Gateway, ClusterIssuer, PVCs, Ollama
    ├── k8s/app/                      # per-release (kustomize): server + web + ConfigMap
    └── scripts/                      # start.sh · stop.sh · ensure-cluster-running.sh
```

---

## Architecture decisions

### Spec-first, codegen both ends

`api/openapi.yaml` is the only source of truth. Both `server/app/api/generated/models.py` (Pydantic v2 via `datamodel-codegen`) and `web-client/src/api.ts` (TypeScript via `openapi-typescript`) are regenerated from it. Hand-written DTOs are forbidden.

```bash
make -C api generate   # regenerate both ends
make -C api check      # CI gate — fails on drift
```

### All agent nodes are async

All three LangGraph nodes are `async def` and use `asyncio.gather` for concurrency:
- `document_search.py` — dispatches multiple `(query, engine)` pairs concurrently
- `evidence_retrieval.py` — fetches all candidate URLs concurrently (capped by `max_concurrent_fetches`); extracts passages concurrently
- `claim_verification.py` — judges all evidence passages concurrently

This keeps the asyncio event loop free so `sse_starlette` can send keep-alive pings and the nginx gateway doesn't time out.

### Structured output via `json_schema`

All LLM calls use `with_structured_output(Model, method="json_schema")`, not the `function_calling` default. On small models (≤7B) like qwen2.5, `function_calling` frequently emits plain text instead of a tool call, causing `PydanticToolsParser` to return `None`. The `json_schema` method uses Ollama's `format` field (or OpenAI-style `response_format` on OpenRouter) to constrain the response.

### LLM provider — OpenRouter or Ollama

`LLM_PROVIDER` selects the backend in `get_llm()` (`app/platform/llm.py`); agents never instantiate a model directly.

| Provider | Client | Notes |
|---|---|---|
| `openrouter` | `langchain_openai.ChatOpenAI` → `https://openrouter.ai/api/v1` | Hosted. Sends `provider.require_parameters: true` so requests only route to providers that honour `json_schema` (otherwise OpenRouter may silently drop it). Optional `OPENROUTER_FALLBACK_MODELS` becomes the `models` array, tried in order if the primary errors. |
| `ollama` | `langchain_ollama.ChatOllama` | Local/in-cluster. Needs the `ollama` compose profile or the bootstrap Ollama Deployment. |

`get_llm()` is `lru_cache`d, so changing LLM settings needs a server restart.

### Search engines

| Engine | Availability | Source type |
|---|---|---|
| `wikipedia` | Always | Encyclopedic |
| `duckduckgo` | Always (no key) | Web |
| `brave` | `BRAVE_API_KEY` required | Web |

The `DocumentSearchAgent` asks the LLM to assign each query to one engine, respecting the `prefer_source` hint (`auto` / `wiki` / `web`). If Brave is unavailable it falls back to DuckDuckGo.

### Authentication — Google OAuth + access/refresh JWT hybrid

Login uses the **Authorization Code Flow**: the browser is redirected to Google's consent screen, Google sends the code back to the server via the browser, the server exchanges it for userinfo using `client_secret` (never exposed to the browser), mints both tokens, and sets them as `httpOnly` cookies on the redirect response.

```
Browser → GET /api/v1/auth/google/login → 302 to Google
Google  → 302 /api/v1/auth/google/callback?code=...
Server  → exchange code + client_secret → userinfo → upsert User
        → mint access JWT (15 min) + opaque refresh token (14 days)
        → store refresh token SHA-256 hash in SQLite RefreshToken table
        → Set-Cookie: access_token (Path=/) + refresh_token (Path=/api/v1/auth)
        → 302 to frontend /
SPA     → GET /api/v1/auth/me → hydrate Redux auth state
```

**Token model:**
- **Access JWT** — short-lived (15 min), stateless, verified by signature alone (no DB hit per request). Carries `sub` (user_id) and `email`.
- **Refresh token** — long-lived (14 days), opaque random string. Only its SHA-256 hash is stored in SQLite. Rotated on every use — old row revoked, new row inserted. Expired rows are deleted on server startup.

**Cookie security:** both cookies are `httpOnly` (JS cannot read them), `SameSite=strict` for auth cookies, `SameSite=lax` for the Authlib session cookie (needed so Google's redirect carries the state cookie back). `Secure=true` in production.

**Frontend:** `src/lib/client.ts` adds `credentials: "include"` so cookies ride along, and implements a single-flight 401 → `POST /refresh` → retry interceptor so the user never sees a session expiry.

### SSE pairing enforced in code

OpenAPI 3.1 can't bind an SSE event name to a payload schema. The pairing is enforced in two places:
- **Backend** — `EVENT_PAYLOAD: dict[SseEventType, type[BaseModel] | None]` registry + `@overload` signatures on `sse()` in `verify.py`
- **Frontend** — `SsePayloadMap` + `_EnsureEveryEventCovered` compile-time guard in `src/types/sse.ts`

Adding a new event requires updating both; the guards make silent drift impossible.

### Frontend streaming

`factcheckActions.ts` POSTs to `/api/v1/verify` with `parseAs: "stream"` (not `EventSource`, which is GET-only). The response `ReadableStream` is parsed for `event:`/`data:` lines and one Redux action is dispatched per SSE event. The reducer accumulates `progress.{queries, candidates, passages, passageVerdicts}`; `AgentTimeline.tsx` renders incrementally.

---

## Configuration reference

`server/app/platform/config.py` — all values overridable via env or `server/.env`:

| Setting | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `openrouter` |
| `OPENROUTER_API_KEY` | `""` | Required when `LLM_PROVIDER=openrouter` — [openrouter.ai/keys](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | `""` | Model slug, e.g. `anthropic/claude-haiku-4.5` |
| `OPENROUTER_FALLBACK_MODELS` | `""` | Comma-separated slugs tried in order after the primary fails (e.g. `:free` models) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override only for a proxy |
| `OLLAMA_HOST` | `""` | e.g. `http://localhost:11434` (when `LLM_PROVIDER=ollama`) |
| `OLLAMA_MODEL` | `""` | e.g. `qwen2.5:7b-instruct` |
| `OLLAMA_NUM_CTX` | `8192` | LLM context window (tokens) |
| `BRAVE_API_KEY` | `""` | Enables Brave search engine |
| `SEARCH_RESULTS_PER_QUERY` | `3` | Search hits per query |
| `MAX_CONCURRENT_FETCHES` | `3` | Parallel URL fetches |
| `HTTP_TIMEOUT_SECONDS` | `20.0` | Per-request HTTP timeout |
| `DATABASE_URL` | — | SQLite URL (async SQLAlchemy) |
| `CORS_ORIGINS` | — | Comma-separated allowed origins |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `OAUTH_REDIRECT_URI` | `http://localhost:5173/api/v1/auth/google/callback` | Must match Google Cloud Console |
| `FRONTEND_URL` | `http://localhost:5173/` | Where server redirects after login |
| `JWT_SECRET` | — | ≥32-char random secret for access token signing |
| `SESSION_SECRET` | — | ≥32-char random secret for Authlib session cookie |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | Access JWT lifetime (15 min) |
| `REFRESH_TOKEN_TTL_SECONDS` | `1209600` | Refresh token lifetime (14 days) |
| `COOKIE_SECURE` | `false` | Set `true` in production (HTTPS only) |
| `COOKIE_SAMESITE` | `strict` | SameSite policy for auth cookies |

---

## Running locally

```bash
# Backend
cd server && cp .env.example .env
#   OpenRouter: LLM_PROVIDER=openrouter, OPENROUTER_API_KEY, OPENROUTER_MODEL
#   Ollama:     LLM_PROVIDER=ollama, OLLAMA_HOST, OLLAMA_MODEL  (+ `docker compose --profile ollama up -d ollama` from repo root)
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd web-client && npm install && npm start   # → http://localhost:5173
```

Full Docker Compose (all services):
```bash
docker compose up -d --build                    # OpenRouter mode (default): server + web
docker compose --profile ollama up -d --build   # also starts Ollama + pulls the model on first run
# → http://localhost (nginx + React), http://localhost:8000 (FastAPI)
```

Compose pins `CORS_ORIGINS`, `FRONTEND_URL` and `OAUTH_REDIRECT_URI` to `http://localhost…` (overriding `server/.env`), so register `http://localhost/api/v1/auth/google/callback` as an authorized redirect URI. `.env` edits need `docker compose up -d --force-recreate server`; code changes need `--build`.
