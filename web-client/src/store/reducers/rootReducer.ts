import { combineReducers } from "@reduxjs/toolkit";
import factcheckReducer from "~/store/reducers/factcheckReducer";
import authReducer from "~/store/reducers/authReducer";

const rootReducer = combineReducers({
  factcheck: factcheckReducer,
  auth: authReducer,
});

export type RootState = ReturnType<typeof rootReducer>;

export default rootReducer;
