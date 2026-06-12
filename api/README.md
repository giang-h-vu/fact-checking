# API Contract

This directory is the **single source of truth** for the public API surface of the fact-checking system. The spec and all of its tooling live here — never duplicated inside individual services.

```
api/
├── openapi.yaml          # the contract — the only file you should hand-edit here
├── Makefile              # make generate | lint | check | clean
└── scripts/
    ├── codegen.sh        # regenerates every downstream artefact
    ├── package.json      # pins JS-based generators (Redocly, openapi-typescript)
    └── redocly.yaml      # Redocly lint config
```

## How it works

Both services consume types generated from the spec — neither defines its own request/response shapes:

```
api/openapi.yaml ──► datamodel-codegen   ──► server/app/api/generated/models.py  (Pydantic v2)
                 └─► openapi-typescript  ──► web-client/src/api.ts               (TS types)
```

Strictly one-way. Services consume; they never write back into `api/`.

| Side | Generator | Output |
|---|---|---|
| Backend (Python) | `datamodel-codegen` | Pydantic v2 **models only** → `server/app/api/generated/models.py`. Routers are hand-written in `server/app/api/` and import these models. |
| Frontend (TS) | `openapi-typescript` | Type-only file → `web-client/src/api.ts`, consumed via `openapi-fetch` and the Redux actions. |

Hand-written DTOs are forbidden and instead added to the spec.

## SSE events are part of the contract

The `/api/v1/verify` endpoint returns `text/event-stream`. OpenAPI can't bind an SSE event *name* to a payload schema, so the spec declares an `SseEventType` enum plus one schema per event payload (`SearchStartedPayload`, `CandidatesFoundPayload`, `PassageFoundPayload`, `PassageVerdictPayload`, `FinalVerdictPayload`). Each side then enforces the name→payload pairing itself:

- **Backend**: the `EVENT_PAYLOAD` registry + typed `sse()` overloads in `server/app/api/verify.py`
- **Frontend**: the `SsePayloadMap` in `web-client/src/types/sse.ts`, with a compile-time exhaustiveness guard

Both are checked (a backend test and a frontend build error respectively) so a new event without a payload schema cannot ship.

## Common tasks

Run these from the **repo root**:

| What you want | Command |
|---|---|
| Lint the spec | `make -C api lint` |
| Regenerate types after editing the spec | `make -C api generate` |
| Verify CI will pass | `make -C api check` |
| Delete generated artefacts (force full regen) | `make -C api clean` |

`make check` is the gate: it regenerates and fails if the working tree differs from what's committed. Drift between spec and generated code cannot land on `main`.

## Editing the spec

1. Edit `openapi.yaml`.
2. `make -C api lint` — must pass before continuing.
3. `make -C api generate` — produces fresh types for both services.
4. Commit `openapi.yaml` **together with** the regenerated files in the same change.
