# API Contract

This directory is the **single source of truth** for the public API surface of the fact-checking system. The spec and all of its tooling live here — never duplicated inside individual services.

```
api/
├── openapi.yaml          # the contract — the only file you should hand-edit here
└── scripts/
    ├── Makefile          # make generate | lint | check | clean
    ├── codegen.sh        # regenerates every downstream artefact
    ├── package.json      # pins JS-based generators (Redocly, openapi-typescript)
    └── redocly.yaml      # Redocly lint config
```

## Information flow

```
api/openapi.yaml ──► fastapi-code-generator ──► server/app/api/generated/
                 └─► openapi-typescript     ──► web-client/src/api.ts
```

Strictly one-way. Services consume; they never write back into `api/`.

## Common tasks

Run these from the **repo root**:

| What you want | Command |
|---|---|
| Lint the spec | `make -C api/scripts lint` |
| Regenerate stubs after editing the spec | `make -C api/scripts generate` |
| Verify CI will pass | `make -C api/scripts check` |
| Delete generated artefacts (force full regen) | `make -C api/scripts clean` |

Or `cd api/scripts` and drop the `make -C api/scripts` prefix.

`make check` is the gate: it regenerates and fails if the working tree differs from what's committed. Drift between spec and generated code cannot land on `main`.

## Editing the spec

1. Edit `openapi.yaml`.
2. `make -C api/scripts lint` — must pass before continuing.
3. `make -C api/scripts generate` — produces fresh stubs in both services.
4. Commit `openapi.yaml` **together with** the regenerated files in the same change.

## Why generators?

| Side | Generator | Output |
|---|---|---|
| Backend (Python) | `fastapi-code-generator` (`fastapi-codegen`) | `APIRouter` stubs + Pydantic v2 models → `server/app/api/generated/`. Route bodies live in `server/app/api/` and are bound to the generated routers at startup. |
| Frontend (TS) | `openapi-typescript` | Type-only file → `web-client/src/api.ts`, consumed by Redux actions. |

Hand-written DTOs are forbidden (project rule). If you find yourself writing a request/response model by hand, add it to the spec instead.

## SSE caveat

The `/api/v1/verify` endpoint returns `text/event-stream`. JSON Schema can't express SSE frame structure, so the response body is typed as `string` and the per-event payloads are documented in the operation description. Both ends parse SSE manually:

- **Backend**: `sse-starlette` in `server/app/api/verify.py`
- **Frontend**: native `fetch` + `ReadableStream` reader in `web-client/src/store/actions/factcheckActions.js` (not `EventSource` — that's GET-only)
