import { Dispatch } from "redux";
import client from "~/lib/client";
import type { VerifyRequest, SseEventType, HistoryItem } from "~/types/api";
import type { SsePayloadMap } from "~/types/sse";

export const WILL_CHECK_FACT     = "AGENT/WILL_CHECK_FACT" as const;
export const SEARCH_STARTED      = "AGENT/SEARCH_STARTED" as const;
export const CANDIDATES_FOUND    = "AGENT/CANDIDATES_FOUND" as const;
export const PASSAGE_FOUND       = "AGENT/PASSAGE_FOUND" as const;
export const PASSAGE_VERDICT     = "AGENT/PASSAGE_VERDICT" as const;
export const FINAL_VERDICT       = "AGENT/FINAL_VERDICT" as const;
export const STREAM_DONE         = "AGENT/STREAM_DONE" as const;
export const STREAM_ERROR        = "AGENT/STREAM_ERROR" as const;
export const WILL_GET_HISTORY    = "AGENT/WILL_GET_HISTORY" as const;
export const GET_HISTORY_SUCCESS = "AGENT/GET_HISTORY_SUCCESS" as const;
export const GET_HISTORY_FAILURE = "AGENT/GET_HISTORY_FAILURE" as const;

const SSE_TO_ACTION: Record<SseEventType, string> = {
  search_started:    SEARCH_STARTED,
  candidates_found:  CANDIDATES_FOUND,
  passage_found:     PASSAGE_FOUND,
  passage_verdict:   PASSAGE_VERDICT,
  final_verdict:     FINAL_VERDICT,
  done:              STREAM_DONE,
  error:             STREAM_ERROR,
};

/**
 * Every action the factcheck reducer handles, as a discriminated union on
 * `type`. The SSE-driven variants carry payloads generated from the OpenAPI
 * spec (via SsePayloadMap), so the reducer narrows action.data per event.
 */
export type FactcheckAction =
  | { type: typeof WILL_CHECK_FACT; claim: string }
  | { type: typeof SEARCH_STARTED; data: SsePayloadMap["search_started"] }
  | { type: typeof CANDIDATES_FOUND; data: SsePayloadMap["candidates_found"] }
  | { type: typeof PASSAGE_FOUND; data: SsePayloadMap["passage_found"] }
  | { type: typeof PASSAGE_VERDICT; data: SsePayloadMap["passage_verdict"] }
  | { type: typeof FINAL_VERDICT; data: SsePayloadMap["final_verdict"] }
  | { type: typeof STREAM_DONE }
  | { type: typeof STREAM_ERROR; data: { message: string } }
  | { type: typeof WILL_GET_HISTORY }
  | { type: typeof GET_HISTORY_SUCCESS; data: HistoryItem[] }
  | { type: typeof GET_HISTORY_FAILURE; data: { message: string } };

export const checkFact = ({ claim, prefer_source = "auto" }: VerifyRequest) => {
  return async (dispatch: Dispatch): Promise<void> => {
    dispatch({ type: WILL_CHECK_FACT, claim });

    const { data: stream, response } = await client.POST("/api/v1/verify", {
      body: { claim, prefer_source },
      parseAs: "stream",
      headers: { 
        Accept: "text/event-stream" 
      },
    }).catch((e: Error) => {
      dispatch({ type: STREAM_ERROR, data: { message: e.message } });
      return { data: null, response: null };
    });

    if (!response?.ok || !stream) {
      dispatch({ type: STREAM_ERROR, data: { message: `HTTP ${response?.status ?? "unknown"}` } });
      return;
    }

    const reader = (stream as ReadableStream<Uint8Array>).getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      while (true) {
        const { value, done } = await reader.read();
        
        if (done){
          break;
        }
        buffer += decoder.decode(value, { stream: true });

        let frameEnd: number;
        while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, frameEnd);
          buffer = buffer.slice(frameEnd + 2);
          dispatchFrame(dispatch, frame);
        }
      }
    } catch (e) {
      dispatch({ type: STREAM_ERROR, data: { message: (e as Error).message } });
    }
  };
};

function dispatchFrame(dispatch: Dispatch, frame: string): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  const actionType = SSE_TO_ACTION[event as SseEventType];
  if (!actionType) return;

  let data: unknown = null;
  if (dataLines.length) {
    try { data = JSON.parse(dataLines.join("\n")); }
    catch { data = { raw: dataLines.join("\n") }; }
  }
  dispatch({ type: actionType, data });
}

export const getHistory = () => {
  return async (dispatch: Dispatch): Promise<void> => {
    dispatch({ type: WILL_GET_HISTORY });
    const { data, error } = await client.GET("/api/v1/history", {});
    if (error) {
      dispatch({ type: GET_HISTORY_FAILURE, data: error });
    } else {
      dispatch({ type: GET_HISTORY_SUCCESS, data: data.items });
    }
  };
};
