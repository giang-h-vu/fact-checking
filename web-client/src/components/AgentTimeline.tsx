import React from "react";
import { useSelector } from "react-redux";
import { List, ListItem, ListItemText, Chip, Typography, LinearProgress, Fade } from "@mui/material";
import { styled } from "@mui/material/styles";
import type { RootState } from "~/store/reducers/rootReducer";
import { CardBox, PassageSpan } from "~/components/StyledWrappers";
import VerdictChip from "~/components/VerdictChip";

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
      {fetchingAnswer && <LinearProgress sx={{ mt: 1 }} />}

      {queries.length > 0 && (
        <Fade in appear>
          <Section>
            <Typography variant="subtitle2">Search queries</Typography>
            {queries.map((q, i) => (
              <Chip key={i} label={q} sx={{ mr: 0.5, mb: 0.5 }} size="small" />
            ))}
          </Section>
        </Fade>
      )}

      {candidates.length > 0 && (
        <Fade in appear>
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
        </Fade>
      )}

      {passages.length > 0 && (
        <Fade in appear>
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
        </Fade>
      )}

      {passageVerdicts.length > 0 && (
        <Fade in appear>
          <Section>
            <Typography variant="subtitle2">Per-passage verdicts ({passageVerdicts.length})</Typography>
            <List dense>
              {passageVerdicts.map((v, i) => (
                <ListItem key={i} disableGutters>
                  <VerdictChip verdict={v.label} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
                  <ListItemText primary={v.reasoning} secondary={v.url} />
                </ListItem>
              ))}
            </List>
          </Section>
        </Fade>
      )}
    </CardBox>
  );
}
