import { describe, it, expect } from "vitest";
import factcheckReducer from "~/store/reducers/factcheckReducer";
import {
  WILL_CHECK_FACT,
  PLAN_CREATED,
  SEARCH_STARTED,
  CANDIDATES_FOUND,
} from "~/store/actions/factcheckActions";

const hit = (url: string) => ({ url, title: url, source: "wikipedia" as const });

describe("factcheckReducer progress", () => {
  it("stores the plan", () => {
    const state = factcheckReducer(undefined, {
      type: PLAN_CREATED,
      data: { subclaims: ["a", "b"] },
    });
    expect(state.progress.plan).toEqual(["a", "b"]);
  });

  it("accumulates queries across searches", () => {
    let state = factcheckReducer(undefined, { type: SEARCH_STARTED, data: { queries: ["q1"] } });
    state = factcheckReducer(state, { type: SEARCH_STARTED, data: { queries: ["q2"] } });
    expect(state.progress.queries).toEqual(["q1", "q2"]);
  });

  it("accumulates candidates without duplicating a URL", () => {
    let state = factcheckReducer(undefined, {
      type: CANDIDATES_FOUND,
      data: { items: [hit("u1"), hit("u2")] },
    });
    state = factcheckReducer(state, {
      type: CANDIDATES_FOUND,
      data: { items: [hit("u2"), hit("u3")] },
    });
    expect(state.progress.candidates.map((c) => c.url)).toEqual(["u1", "u2", "u3"]);
  });

  it("resets the plan when a new claim starts", () => {
    let state = factcheckReducer(undefined, { type: PLAN_CREATED, data: { subclaims: ["a"] } });
    state = factcheckReducer(state, { type: WILL_CHECK_FACT, claim: "next" });
    expect(state.progress.plan).toEqual([]);
  });
});
