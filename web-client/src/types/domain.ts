import type { Verdict, Citation, SearchCandidate, HistoryItem } from "~/types/api";

export interface Passage {
  url: string;
  title?: string;
  passage: string;
}

export interface PassageVerdict {
  url: string;
  label: Verdict;
  reasoning: string;
}

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
