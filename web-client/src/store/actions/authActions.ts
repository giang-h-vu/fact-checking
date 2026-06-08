import { Dispatch } from "redux";
import client from "~/lib/client";
import type { User } from "~/types/api";

export const FETCH_ME_SUCCESS = "AUTH/FETCH_ME_SUCCESS" as const;
export const FETCH_ME_FAILURE = "AUTH/FETCH_ME_FAILURE" as const;
export const LOGOUT            = "AUTH/LOGOUT" as const;

export type AuthAction =
  | { type: typeof FETCH_ME_SUCCESS; data: User }
  | { type: typeof FETCH_ME_FAILURE }
  | { type: typeof LOGOUT };

/** Hydrate auth state on app load. No loading dispatch.
 *  The store starts in "loading", and re-validating an
 *  already-authenticated session shouldn't flash the login screen.
**/
export const fetchMe = () => {
  return async (dispatch: Dispatch): Promise<void> => {
    const { data, error } = await client.GET("/api/v1/auth/me", {});
    if (error || !data) {
      dispatch({ type: FETCH_ME_FAILURE });
    } else {
      dispatch({ type: FETCH_ME_SUCCESS, data });
    }
  };
};

export const logout = () => {
  return async (dispatch: Dispatch): Promise<void> => {
    await client.POST("/api/v1/auth/logout", {});
    dispatch({ type: LOGOUT });
  };
};
