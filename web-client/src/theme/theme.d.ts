import "@mui/material/styles";
import type { Verdict } from "~/types/api";

// Each verdict label is a first-class brand token: its own fill + readable text
// colour. Adding it to the palette lets components read theme.palette.verdict[label]
// and keeps verdict styling in one place.
type VerdictPalette = Record<Verdict, { main: string; contrastText: string }>;

// Brand teal — the app's signature colour (sidebar/nav, accents). Lives in the
// palette so Login, Dashboard, etc. read one source instead of duplicating hex.
type BrandPalette = { main: string; dark: string };

declare module "@mui/material/styles" {
  interface Palette {
    verdict: VerdictPalette;
    brand: BrandPalette;
  }
  interface PaletteOptions {
    verdict?: VerdictPalette;
    brand?: BrandPalette;
  }
}
