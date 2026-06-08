import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "~/utils/test-utils";
import App from "./App";

// App dispatches fetchMe() on mount. Stub it to a no-op thunk so the test
// drives auth purely through preloadedState.
vi.mock("~/store/actions/authActions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("~/store/actions/authActions")>();
  return { ...actual, fetchMe: () => () => Promise.resolve() };
});

describe("App", () => {
  it("renders the app title when authenticated", () => {
    renderWithProviders(<App />, {
      preloadedState: {
        auth: { status: "authenticated", user: { id: 1, email: "a@b.c", name: "Tester" } },
      },
    });
    expect(screen.getByText(/fact-checking tool/i)).toBeDefined();
  });

  it("shows the login page when unauthenticated", () => {
    renderWithProviders(<App />, {
      preloadedState: { auth: { status: "unauthenticated", user: null } },
    });
    expect(screen.getByText(/continue with google/i)).toBeDefined();
  });
});
