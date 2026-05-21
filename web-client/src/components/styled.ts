import { Paper, Typography, Divider } from "@mui/material";
import { styled } from "@mui/material/styles";

export const CardBox = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(2),
  marginBottom: theme.spacing(2),
}));

export const CitationBox = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(1),
  marginTop: theme.spacing(1),
}));

export const PassageText = styled(Typography)({
  fontStyle: "italic",
  color: "#555",
  marginTop: 4,
});

export const PassageSpan = styled("span")({
  fontStyle: "italic",
  color: "#555",
});

export const SectionDivider = styled(Divider)({
  marginTop: "2rem",
  marginBottom: "2rem",
});
