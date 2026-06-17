import type { Reducer } from "@reduxjs/toolkit";
import type { FactcheckState, Progress } from "~/types/domain";
import {
  WILL_CHECK_FACT,
  SEARCH_STARTED,
  CANDIDATES_FOUND,
  PASSAGE_FOUND,
  PASSAGE_VERDICT,
  FINAL_VERDICT,
  STREAM_DONE,
  STREAM_ERROR,
  WILL_GET_HISTORY,
  GET_HISTORY_SUCCESS,
  GET_HISTORY_FAILURE,
} from "~/store/actions/factcheckActions";
import type { FactcheckAction } from "~/store/actions/factcheckActions";

export type { FactcheckState };

const emptyProgress = (): Progress => ({
  queries: [],
  candidates: [],
  passages: [],
  passageVerdicts: [],
});

const initState: FactcheckState = {
  claim: "",
  fetchingAnswer: false,
  progress: emptyProgress(),
  verdict: "",
  citations: [],
  history: [],
  error: null,
};

const factcheckReducer = (
  state: FactcheckState = initState,
  action: FactcheckAction,
): FactcheckState => {
  switch (action.type) {
    case WILL_CHECK_FACT:
      return {
        ...state,
        claim: action.claim,
        fetchingAnswer: true,
        progress: emptyProgress(),
        verdict: "",
        citations: [],
        error: null,
      };
    case SEARCH_STARTED:
      return { ...state, progress: { ...state.progress, queries: action.data.queries ?? [] } };
    case CANDIDATES_FOUND:
      return { ...state, progress: { ...state.progress, candidates: action.data.items ?? [] } };
    case PASSAGE_FOUND:
      return {
        ...state,
        progress: { ...state.progress, passages: [...state.progress.passages, action.data] },
      };
    case PASSAGE_VERDICT:
      return {
        ...state,
        progress: {
          ...state.progress,
          passageVerdicts: [...state.progress.passageVerdicts, action.data],
        },
      };
    case FINAL_VERDICT:
      return { ...state, verdict: action.data.verdict, citations: action.data.citations ?? [] };
    case STREAM_DONE:
      return { ...state, fetchingAnswer: false };
    case STREAM_ERROR:
      return { ...state, fetchingAnswer: false, error: action.data };
    case WILL_GET_HISTORY:
      return state;
    case GET_HISTORY_SUCCESS:
      return { ...state, history: action.data };
    case GET_HISTORY_FAILURE:
      return { ...state, error: action.data };
    default:
      return state;
  }
};

// The body narrows action via FactcheckAction, but RTK's combineReducers
// requires reducers to accept UnknownAction — cast at the boundary so the
// inferred RootState stays FactcheckState rather than collapsing to never.
export default factcheckReducer as Reducer<FactcheckState>;
