
import { createTheme } from '@mui/material/styles';
import { common } from '@mui/material/colors';
import shadows from '~/theme/shadows';
import typography from '~/theme/typography';

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