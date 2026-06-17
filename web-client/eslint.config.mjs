import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Not linted: build output and the generated API client (regenerated from
  // api/openapi.yaml — linting/--fix here would trip the codegen-drift gate).
  { ignores: ["dist", "src/api.ts"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    rules: {
      // Allow intentionally-unused `_`-prefixed names, e.g. the compile-time
      // exhaustiveness guard `_EnsureEveryEventCovered` in src/types/sse.ts.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Test files & helpers aren't part of the Fast Refresh graph, so the
    // "only export components" constraint doesn't apply (e.g. test-utils
    // re-exports @testing-library/react).
    files: ["**/*.test.{ts,tsx}", "**/test-utils.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
);
