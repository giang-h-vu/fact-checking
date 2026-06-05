import theme from "~/theme";
import type { Verdict } from "~/types/api";

// Colours now live in the theme palette (theme.palette.verdict). 
// These helpers are the single read-path for verdict styling.
export const verdictColor = (verdict: Verdict): string =>
  theme.palette.verdict[verdict].main;

export const verdictTextColor = (verdict: Verdict): string =>
  theme.palette.verdict[verdict].contrastText;

// Human-readable labels for the raw verdict enum values.
const VERDICT_LABELS: Record<Verdict, string> = {
  SUPPORTED: "Supported",
  REFUTED: "Refuted",
  NOT_ENOUGH_INFO: "Not Enough Information",
};

export const verdictLabel = (verdict: Verdict): string => VERDICT_LABELS[verdict];
