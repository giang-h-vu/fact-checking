import { Verdict } from "~/types/api";

export const verdictColor = (verdict: Verdict): string => {
  switch (verdict) {
    case "SUPPORTED":       return "#2e7d32";
    case "REFUTED":         return "#c62828";
    case "NOT_ENOUGH_INFO": return "#757575";
    default:                throw new Error(`Unknown verdict: ${verdict}`);
  }
};
