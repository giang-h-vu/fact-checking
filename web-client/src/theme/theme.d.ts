import "@mui/material/styles";
import type { Verdict } from "~/types/api";

// Each verdict label is a first-class brand token: its own fill + readable text
// colour. Adding it to the palette lets components read theme.palette.verdict[label]
// and keeps verdict styling in one place.
type VerdictPalette = Record<Verdict, { main: string; contrastText: string }>;

declare module "@mui/material/styles" {
  interface Palette {
    verdict: VerdictPalette;
  }
  interface PaletteOptions {
    verdict?: VerdictPalette;
  }
}
