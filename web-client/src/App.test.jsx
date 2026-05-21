import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "~/test-utils";
import App from "./App";

describe("App", () => {
  it("renders app title", () => {
    renderWithProviders(<App />);
    const title = screen.getByText(/fact-checking tool/i);
    expect(title).toBeDefined();
  });
});
