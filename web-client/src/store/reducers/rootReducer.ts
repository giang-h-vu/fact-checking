import { combineReducers } from "@reduxjs/toolkit";
import factcheckReducer from "~/store/reducers/factcheckReducer";

const rootReducer = combineReducers({
  factcheck: factcheckReducer,
});

export type RootState = ReturnType<typeof rootReducer>;

export default rootReducer;
