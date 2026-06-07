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

export const PassageText = styled(Typography)(({ theme }) => ({
  fontStyle: "italic",
  color: theme.palette.text.secondary,
  marginTop: theme.spacing(0.5),
}));

export const PassageSpan = styled("span")(({ theme }) => ({
  fontStyle: "italic",
  color: theme.palette.text.secondary,
}));

export const SectionDivider = styled(Divider)({
  marginTop: "1rem",
  marginBottom: "0rem",
});
