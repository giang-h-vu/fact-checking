import { Chip } from "@mui/material";
import type { ChipProps } from "@mui/material";
import type { ReactNode } from "react";
import type { Verdict } from "~/types/api";
import { verdictColor, verdictTextColor, verdictLabel } from "~/utils/verdict";

type VerdictChipProps = Omit<ChipProps, "color" | "label"> & {
  verdict: Verdict;
  label?: ReactNode;
};

export default function VerdictChip({ verdict, label, sx, ...rest }: VerdictChipProps) {
  return (
    <Chip
      label={label ?? verdictLabel(verdict)}
      sx={{ bgcolor: verdictColor(verdict), color: verdictTextColor(verdict), ...sx }}
      {...rest}
    />
  );
}
