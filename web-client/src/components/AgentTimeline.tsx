import React from "react";
import { useSelector } from "react-redux";
import { List, ListItem, ListItemText, Chip, Typography, LinearProgress } from "@mui/material";
import { styled } from "@mui/material/styles";
import type { RootState } from "~/store/reducers/rootReducer";
import { CardBox, PassageSpan } from "~/components/styled";
import { verdictColor } from "~/utils/verdict";

const Section = styled("div")(({ theme }) => ({
  marginTop: theme.spacing(1),
}));

export default function AgentTimeline() {
  const progress       = useSelector((state: RootState) => state.factcheck.progress);
  const fetchingAnswer = useSelector((state: RootState) => state.factcheck.fetchingAnswer);
  const verdict        = useSelector((state: RootState) => state.factcheck.verdict);

  const { queries, candidates, passages, passageVerdicts } = progress;

  if (!queries.length && !candidates.length && !passages.length && !passageVerdicts.length && !verdict) {
    return null;
  }

  return (
    <CardBox>
      <Typography variant="h6">Agent progress</Typography>
      {fetchingAnswer && <LinearProgress style={{ marginTop: 8 }} />}

      {queries.length > 0 && (
        <Section>
          <Typography variant="subtitle2">Search queries</Typography>
          {queries.map((q, i) => (
            <Chip key={i} label={q} sx={{ mr: 0.5, mb: 0.5 }} size="small" />
          ))}
        </Section>
      )}

      {candidates.length > 0 && (
        <Section>
          <Typography variant="subtitle2">Candidate sources ({candidates.length})</Typography>
          <List dense>
            {candidates.map((c, i) => (
              <ListItem key={i} disableGutters>
                <ListItemText
                  primary={<a href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}</a>}
                  secondary={`source: ${c.source}`}
                />
              </ListItem>
            ))}
          </List>
        </Section>
      )}

      {passages.length > 0 && (
        <Section>
          <Typography variant="subtitle2">Extracted passages ({passages.length})</Typography>
          <List dense>
            {passages.map((p, i) => (
              <ListItem key={i} disableGutters>
                <ListItemText
                  primary={p.title || p.url}
                  secondary={<PassageSpan>"{p.passage}"</PassageSpan>}
                />
              </ListItem>
            ))}
          </List>
        </Section>
      )}

      {passageVerdicts.length > 0 && (
        <Section>
          <Typography variant="subtitle2">Per-passage verdicts ({passageVerdicts.length})</Typography>
          <List dense>
            {passageVerdicts.map((v, i) => (
              <ListItem key={i} disableGutters>
                <Chip
                  label={v.label}
                  size="small"
                  sx={{ mr: 0.5, mb: 0.5 }}
                  style={{ backgroundColor: verdictColor(v.label), color: "white" }}
                />
                <ListItemText primary={v.reasoning} secondary={v.url} />
              </ListItem>
            ))}
          </List>
        </Section>
      )}
    </CardBox>
  );
}
