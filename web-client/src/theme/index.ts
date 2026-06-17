// Self-hosted Poppins. typography.fontFamily references
// Poppins, so the weights it uses must actually be loaded here or the browser
// silently falls back and the type scale renders in the wrong font.
import "@fontsource/poppins/400.css";
import "@fontsource/poppins/500.css";
import "@fontsource/poppins/600.css";

import { createTheme } from "@mui/material/styles";
import { common } from "@mui/material/colors";
import shadows from "~/theme/shadows";
import typography from "~/theme/typography";

const theme = createTheme({
  palette: {
    background: {
      default: "#F4F6F8",
      paper: common.white,
    },
    primary: {
      contrastText: "#ffffff",
      main: "#0A47C4",
    },
    text: {
      primary: "#172b4d",
      secondary: "#6b778c",
    },
    secondary: {
      main: "#F2F9FF",
    },
    // Domain tokens for the three verdict states. Verdict is a first-class concept in this app so it
    // gets its own named palette rather than borrowing the semantic one.
    verdict: {
      SUPPORTED: { main: "#2e7d32", contrastText: common.white },
      REFUTED: { main: "#c62828", contrastText: common.white },
      NOT_ENOUGH_INFO: { main: "#757575", contrastText: common.white },
    },
    // Signature teal used by the sidebar/nav and the login screen.
    brand: { main: "#10A19D", dark: "#0B7A77" },
  },
  components: {
    MuiTableRow: {
      styleOverrides: {
        root: { "&.Mui-selected, &.Mui-selected:hover": { backgroundColor: "#F2F9FF" } },
      },
    },
    MuiCheckbox: {
      styleOverrides: {
        root: { "&.Mui-checked": { color: "#0A47C4" } },
      },
    },
  },
  shadows,
  typography,
});

export default theme;
