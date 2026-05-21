# Fact-Checking

Agent-driven fact-checking service. A claim is routed through three LangGraph agents — document search → evidence retrieval → claim verification — and a verdict (`SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO`) is returned with citations. Progress streams to the UI over Server-Sent Events.

## Repo layout

| Path | Purpose |
|---|---|
| [`api/`](api/README.md) | OpenAPI spec (`api/openapi.yaml`) + codegen tooling (`api/scripts/`). Single source of truth for the public contract. |
| [`server/`](server/README.md) | FastAPI + LangGraph + Ollama backend. |
| [`web-client/`](web-client/README.md) | React + Redux web client. |
| [`infra/`](infra/README.md) | Infrastructure configuration (Docker Compose for local dev). |

Information flows one-way: `api/openapi.yaml` → generators → `server/` and `web-client/`. Both ends regenerate from the spec; hand-written DTOs are forbidden.

## Quick start

```bash
# 1. Start Ollama
cd infra/compose && docker compose up -d
docker exec -it ollama ollama pull qwen2.5:7b-instruct
cd ../..

# 2. Backend
cd server && uv sync && cp .env.example .env
uv run uvicorn app.main:app --reload --port 8000   # → http://localhost:8000/docs

# 3. Web client (second terminal)
cd web-client && npm install && npm start           # → http://localhost:3000
```

See [`server/README.md`](server/README.md) and [`web-client/README.md`](web-client/README.md) for full setup, tests, and configuration.

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
