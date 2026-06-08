import { describe, it, expect } from "vitest";
import authReducer from "~/store/reducers/authReducer";
import { FETCH_ME_SUCCESS, FETCH_ME_FAILURE, LOGOUT } from "~/store/actions/authActions";

const user = { id: 1, email: "a@b.c", name: "Tester" };

describe("authReducer", () => {
  it("starts in the loading state", () => {
    const state = authReducer(undefined, { type: "@@INIT" });
    expect(state).toEqual({ user: null, status: "loading" });
  });

  it("becomes authenticated on FETCH_ME_SUCCESS", () => {
    const state = authReducer(undefined, { type: FETCH_ME_SUCCESS, data: user });
    expect(state).toEqual({ user, status: "authenticated" });
  });

  it("becomes unauthenticated on FETCH_ME_FAILURE", () => {
    const state = authReducer(undefined, { type: FETCH_ME_FAILURE });
    expect(state).toEqual({ user: null, status: "unauthenticated" });
  });

  it("clears the user on LOGOUT", () => {
    const loggedIn = { user, status: "authenticated" } as const;
    const state = authReducer(loggedIn, { type: LOGOUT });
    expect(state).toEqual({ user: null, status: "unauthenticated" });
  });
});
