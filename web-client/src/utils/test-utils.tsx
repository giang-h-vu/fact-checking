import { render, RenderOptions } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import rootReducer, { RootState } from "~/store/reducers/rootReducer";
import theme from "~/theme/index";

interface RenderWithProvidersOptions extends Omit<RenderOptions, "wrapper"> {
  preloadedState?: Partial<RootState>;
  route?: string;
}

export function renderWithProviders(
  ui: React.ReactElement,
  { preloadedState = {}, route = "/", ...renderOptions }: RenderWithProvidersOptions = {}
) {
  const store = configureStore({ reducer: rootReducer, preloadedState });
  return render(
    <Provider store={store}>
      <ThemeProvider theme={theme}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </ThemeProvider>
    </Provider>,
    renderOptions
  );
}

export * from "@testing-library/react";
