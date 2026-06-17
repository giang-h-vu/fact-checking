import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { configureStore } from "@reduxjs/toolkit";
import rootReducer from "~/store/reducers/rootReducer";
import { Provider } from "react-redux";

const store = configureStore({ reducer: rootReducer });

const root = createRoot(document.getElementById("root")!);
root.render(
  <Provider store={store}>
    <App />
  </Provider>,
);
