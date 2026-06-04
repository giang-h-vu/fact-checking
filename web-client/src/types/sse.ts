import type { components } from "~/api";
import type { SseEventType } from "~/types/api";

type Schemas = components["schemas"];

/**
 * The `data` payload carried by each named SSE event, keyed by event name.
 * Mirrors the backend EVENT_PAYLOAD registry in app/api/verify.py — both are
 * derived from api/openapi.yaml, so the wire contract has a single source.
 */
export type SsePayloadMap = {
  search_started: Schemas["SearchStartedPayload"];
  candidates_found: Schemas["CandidatesFoundPayload"];
  passage_found: Schemas["PassageFoundPayload"];
  passage_verdict: Schemas["PassageVerdictPayload"];
  final_verdict: Schemas["FinalVerdictPayload"];
  done: Record<string, never>;
  error: Schemas["Error"];
};

/**
 * Compile-time coverage guard: indexing SsePayloadMap by every SseEventType
 * fails to type-check if an event is added to the spec without a payload here.
 */
type _EnsureEveryEventCovered = { [K in SseEventType]: SsePayloadMap[K] };
