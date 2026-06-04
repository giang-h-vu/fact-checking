import type { components } from "~/api";
import type { Verdict, Citation, SearchCandidate, HistoryItem } from "~/types/api";

// Generated from api/openapi.yaml — the SSE passage_found / passage_verdict shapes.
export type Passage = components["schemas"]["PassageFoundPayload"];
export type PassageVerdict = components["schemas"]["PassageVerdictPayload"];

export interface Progress {
  queries: string[];
  candidates: SearchCandidate[];
  passages: Passage[];
  passageVerdicts: PassageVerdict[];
}

export interface FactcheckState {
  claim: string;
  fetchingAnswer: boolean;
  progress: Progress;
  verdict: Verdict | "";
  citations: Citation[];
  history: HistoryItem[];
  error: { message: string } | null;
}
