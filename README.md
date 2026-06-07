# Fact-Checking

Agent-driven fact-checking service. A claim is routed through three LangGraph agents — document search → evidence retrieval → claim verification — and a verdict (`SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO`) is returned with citations. Progress streams to the UI over Server-Sent Events.

## Repo layout

| Path | Purpose |
|---|---|
| [`api/`](api/README.md) | OpenAPI spec (`api/openapi.yaml`) + codegen tooling (`api/scripts/`). Single source of truth for the public contract. |
| [`server/`](server/README.md) | FastAPI + LangGraph + Ollama backend. |
| [`web-client/`](web-client/README.md) | React + Redux web client. |
| `docker-compose.yml` | Full-stack Docker Compose (Ollama + server + web). |
| [`infra/`](infra/README.md) | Cloud infrastructure (Terraform placeholder). |

Information flows one-way: `api/openapi.yaml` → generators → `server/` and `web-client/`. Both ends regenerate from the spec; hand-written DTOs are forbidden.

## Quick start

### Docker (full stack)

The fastest way to run everything. Requires Docker with Compose v2.

```bash
# 1. Build and start all services (Ollama + backend + frontend)
docker compose up -d --build
# The ollama-pull service automatically pulls qwen2.5:7b-instruct on first run.
```

The app is then at **http://localhost**. The backend API is also exposed at `http://localhost:8000`.

| Port | Service |
|---|---|
| `80` | React frontend (nginx) |
| `8000` | FastAPI backend |
| `11434` | Ollama |

```bash
docker compose down        # stop, keep volumes
docker compose down -v     # stop and delete volumes (~5–40 GB)
```

**CPU-only:** remove the `deploy.resources` block in `docker-compose.yml` under the `ollama` service.

### Local dev (Ollama in Docker, server/web native)

Run Ollama in Docker, then start the backend and frontend natively for faster iteration.

```bash
# 1. Start Ollama only
docker compose up -d ollama
docker exec -it ollama ollama pull qwen2.5:7b-instruct

# 2. Backend
cd server && cp .env.example .env && uv sync
uv run uvicorn app.main:app --reload --port 8000   # → http://localhost:8000/docs

# 3. Web client (second terminal)
cd web-client && npm install && npm start           # → http://localhost:5173
```

See [`server/README.md`](server/README.md) and [`web-client/README.md`](web-client/README.md) for full setup, tests, and configuration.

### Model recommendations

| Model | VRAM | Notes |
|---|---|---|
| `llama3.1:70b-instruct` | ~48 GB | Best quality |
| `qwen2.5:7b-instruct` | ~8 GB | Good enough for development |

Structured output (`json_schema` mode) requires Ollama 0.3+. If verdicts are consistently `NOT_ENOUGH_INFO`, the model is usually the cause.

### Configuration

Key environment variables (set in `server/.env`):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | — | Model tag, e.g. `qwen2.5:7b-instruct` |
| `OLLAMA_NUM_CTX` | `8192` | Context window tokens |
| `SEARCH_RESULTS_PER_QUERY` | `3` | Hits per search query |
| `MAX_CONCURRENT_FETCHES` | `3` | Parallel URL fetches |
| `BRAVE_API_KEY` | — | Optional; enables Brave search engine |

## API contract

```bash
make -C api generate   # regenerate server/app/api/generated/ + web-client/src/api.ts
make -C api check      # CI gate — fails on drift
make -C api lint       # Redocly lint only
```

## Project rules
- **Spec-first** — every API change starts in `api/openapi.yaml`.
- **No hand-written DTOs** — `server/app/api/generated/` is generated, never edited.
- **Integration tests hit real APIs / DBs**, not mocks.
- **Short branches** — merge or rebase within 2 days.
