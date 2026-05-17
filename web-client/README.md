# web-client

React + Redux web client for the fact-checking service. Submits claims to the backend, reads the SSE stream as the agents work, and renders live progress before showing the final verdict and citations.

## Stack

- **React 18** (Vite)
- **Redux + redux-thunk** (state management)
- **MUI v5** (components)

## Setup & run

```bash
npm install
npm start    # → http://localhost:5173
```

The backend must be running at `http://localhost:8000`. The Vite dev server proxies `/api` to the backend by default. See [`server/README.md`](../server/README.md) for backend setup.

## Tests

```bash
npm test
```

## Layout

```
src/
├── api.ts                          # GENERATED — do not edit (from api/openapi.yaml)
├── store/
│   ├── actions/
│   │   └── factcheckActions.js     # POSTs to /api/v1/verify, reads SSE stream, dispatches per-event
│   └── reducers/
│       ├── factcheckReducer.js     # accumulates progress; sets verdict + citations on final_verdict
│       └── rootReducer.js          # combines reducers
├── components/
│   ├── SearchInput.jsx             # claim input field + submit
│   ├── AgentTimeline.jsx           # live progress: queries → candidates → passages → verdicts
│   ├── Dashboard.jsx               # layout wrapper (nav + page frame)
│   └── HowItWorks.jsx              # static explanation of the agent pipeline
├── views/
│   ├── Home.jsx                    # search + timeline + final verdict + citations
│   └── History.jsx                 # GET /api/v1/history — past verifications
├── theme/                          # Material-UI theme (typography, shadows, palette)
│   └── index.js
└── App.js                          # route definitions
```

## How streaming works

`factcheckActions.js` uses `fetch` — not `EventSource` — because `EventSource` is GET-only and the verify endpoint is `POST`. The response body is a `ReadableStream`; the action reads it line-by-line, parsing `event:` + `data:` pairs, and dispatches one Redux action per SSE event.

The reducer accumulates state incrementally:

| SSE event | Reducer action |
|---|---|
| `search_started` | append queries to `progress.queries` |
| `candidates_found` | append to `progress.candidates` |
| `passage_found` | append to `progress.passages` |
| `passage_verdict` | append to `progress.passageVerdicts` |
| `final_verdict` | set `verdict` + `citations` |
| `done` | set `status = done` |
| `error` | set `error` message |

`AgentTimeline.jsx` renders `progress.*` as it arrives. `Home.jsx` shows the verdict block once `final_verdict` lands.

## Generated types

`src/api.ts` is generated from `api/openapi.yaml` via `openapi-typescript`. Do not edit it by hand — run `make -C api/scripts generate` from the repo root after changing the spec.

## Routes

| Path | View |
|---|---|
| `/` | `Home.jsx` — search + live progress + final verdict |
| `/history` | `History.jsx` — past verifications |
| `/workings` | `HowItWorks.jsx` — static explanation of the agent pipeline |
