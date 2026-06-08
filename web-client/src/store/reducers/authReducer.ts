import type { Reducer } from "@reduxjs/toolkit";
import type { User } from "~/types/api";
import {
  FETCH_ME_SUCCESS, FETCH_ME_FAILURE, LOGOUT,
} from "~/store/actions/authActions";
import type { AuthAction } from "~/store/actions/authActions";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthState {
  user: User | null;
  status: AuthStatus;
}

// Starts "loading" so the app can wait for the initial /me before deciding
// whether to show the login page (avoids a flash of the login screen).
const initState: AuthState = {
  user: null,
  status: "loading",
};

const authReducer = (
  state: AuthState = initState,
  action: AuthAction,
): AuthState => {
  switch (action.type) {
    case FETCH_ME_SUCCESS:
      return { user: action.data, status: "authenticated" };
    case FETCH_ME_FAILURE:
      return { user: null, status: "unauthenticated" };
    case LOGOUT:
      return { user: null, status: "unauthenticated" };
    default:
      return state;
  }
};

export default authReducer as Reducer<AuthState>;
