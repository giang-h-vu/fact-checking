import type { components } from "~/api";

export type Verdict = components["schemas"]["Verdict"];
export type User = components["schemas"]["User"];
export type SseEventType = components["schemas"]["SseEventType"];
export type Citation = components["schemas"]["Citation"];
export type HistoryItem = components["schemas"]["HistoryItem"];
export type SearchCandidate = components["schemas"]["SearchCandidate"];
export type VerifyRequest = components["schemas"]["VerifyRequest"];
export type PreferSource = components["schemas"]["VerifyRequest"]["prefer_source"];
