# web-client

React + Redux web client for the fact-checking service. Submits a claim to the backend, reads the SSE stream as the agents work, and renders a live timeline of queries → sources → passages → judgements before showing the final verdict with citations.

## How it works

### Streaming

`src/store/actions/factcheckActions.ts` POSTs to `/api/v1/verify` through the `openapi-fetch` client (`src/lib/client.ts`) with `parseAs: "stream"` — **not** `EventSource`, which is GET-only. The response body is a `ReadableStream`; the action parses SSE frames (`event:` + `data:` pairs) and dispatches one Redux action per event.

The reducer (`src/store/reducers/factcheckReducer.ts`) accumulates state incrementally:

| SSE event          | Reducer action                       |
| ------------------ | ------------------------------------ |
| `search_started`   | append queries to `progress.queries` |
| `candidates_found` | append to `progress.candidates`      |
| `passage_found`    | append to `progress.passages`        |
| `passage_verdict`  | append to `progress.passageVerdicts` |
| `final_verdict`    | set `verdict` + `citations`          |
| `done`             | set `status = done`                  |
| `error`            | set `error` message                  |

`AgentTimeline.tsx` renders `progress.*` as it arrives; `Home.tsx` shows the verdict block once `final_verdict` lands.

### Type safety end to end

- `src/api.ts` is **generated** from `api/openapi.yaml` (`openapi-typescript`) — never hand-edited.
- `src/types/sse.ts` maps each `SseEventType` → its generated payload (`SsePayloadMap`), with a compile-time guard that fails the build if the spec adds an event without a payload. It mirrors the backend's `EVENT_PAYLOAD` registry.
- Redux actions form a discriminated union (`FactcheckAction`), so the reducer narrows `action.data` per event at compile time — handling `candidates_found` with the wrong payload type is a build error, not a runtime surprise.

### Auth

Google OAuth: `Login.tsx` starts the flow, the backend sets a JWT cookie, and `authActions.ts` tracks the session. Authenticated users get their verification history on `/history`.

## Stack

- **React 18** (Vite)
- **Redux Toolkit** (`configureStore`) + thunks, react-redux
- **MUI v5** (components)
- **TypeScript strict** — `npm run build` runs `tsc -b`; type errors fail the build

## Setup & run

```bash
npm install
npm start    # → http://localhost:5173
```

The backend must be running at `http://localhost:8000`. The Vite dev server proxies `/api` to the backend. See [`server/README.md`](../server/README.md) for backend setup.

## Tests

```bash
npm test         # vitest
npm run build    # type-check + production build
```

## Layout

```
src/
├── api.ts                          # GENERATED — do not edit (from api/openapi.yaml)
├── lib/
│   └── client.ts                   # openapi-fetch client
├── types/
│   ├── api.ts                      # convenience re-exports (Verdict, Citation, …)
│   └── sse.ts                      # SseEventType → payload map + exhaustiveness guard
├── store/
│   ├── actions/
│   │   ├── factcheckActions.ts     # POST /verify, parse SSE stream, dispatch per event
│   │   └── authActions.ts          # login/logout/session
│   └── reducers/
│       ├── factcheckReducer.ts     # accumulates progress; verdict + citations on final_verdict
│       └── rootReducer.ts
├── components/
│   ├── SearchInput.tsx             # claim input + submit
│   ├── AgentTimeline.tsx           # live progress timeline
│   ├── VerdictChip.tsx             # verdict badge
│   └── Dashboard.tsx               # layout wrapper (nav + page frame)
├── pages/
│   ├── Home.tsx                    # search + timeline + final verdict + citations
│   ├── History.tsx                 # GET /api/v1/history — past verifications
│   ├── HowItWorks.tsx              # static explanation of the agent pipeline
│   └── Login.tsx                   # Google OAuth entry
├── theme/                          # MUI theme (typography, shadows, palette)
└── App.tsx                         # route definitions
```

## Routes

| Path        | Page                                                        |
| ----------- | ----------------------------------------------------------- |
| `/`         | `Home.tsx` — search + live progress + final verdict         |
| `/history`  | `History.tsx` — past verifications                          |
| `/workings` | `HowItWorks.tsx` — static explanation of the agent pipeline |
| `/login`    | `Login.tsx` — Google OAuth sign-in                          |

## Regenerating types

After changing `api/openapi.yaml`, run from the repo root:

```bash
make -C api generate   # rewrites src/api.ts (and the backend models)
```
