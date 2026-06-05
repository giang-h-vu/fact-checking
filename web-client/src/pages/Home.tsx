import React from "react";
import { useSelector } from "react-redux";
import { Grid, Typography, Chip } from "@mui/material";
import type { RootState } from "~/store/reducers/rootReducer";
import type { Citation } from "~/types/api";
import SearchInput from "~/components/SearchInput";
import AgentTimeline from "~/components/AgentTimeline";
import { CardBox, CitationBox, PassageText } from "~/components/styled";
import { verdictColor } from "~/utils/verdict";

export default function Home() {
  const claim          = useSelector((state: RootState) => state.factcheck.claim);
  const verdict        = useSelector((state: RootState) => state.factcheck.verdict);
  const citations      = useSelector((state: RootState) => state.factcheck.citations);
  const error          = useSelector((state: RootState) => state.factcheck.error);
  const fetchingAnswer = useSelector((state: RootState) => state.factcheck.fetchingAnswer);

  const resultsRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!fetchingAnswer && (verdict || error)) {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [fetchingAnswer, verdict, error]);

  return (
    <div className="search-and-more">
      <Grid container direction="row" alignItems="stretch" spacing={1} sx={{ mb: "1rem" }}>
        <Grid item xs={12}><SearchInput /></Grid>

        {error && (
          <Grid item xs={12}>
            <CardBox style={{ background: "#ffebee" }}>
              <Typography color="error">{error.message || "Something went wrong"}</Typography>
            </CardBox>
          </Grid>
        )}

        <Grid item xs={12} ref={resultsRef}><AgentTimeline /></Grid>

        {verdict && (
          <Grid item xs={12}>
            <CardBox>
              <Typography variant="subtitle2" color="textSecondary">Claim</Typography>
              <Typography variant="body1" gutterBottom>"{claim}"</Typography>
              <Chip
                label={`Verdict: ${verdict}`}
                style={{ backgroundColor: verdictColor(verdict), color: "white", fontSize: 16 }}
              />
            </CardBox>

            {citations.length > 0 && (
              <>
                <Typography variant="h6" sx={{ ml: "6px" }}>Citations</Typography>
                {citations.map((c: Citation, i: number) => (
                  <CitationBox key={i}>
                    <Chip
                      label={c.label}
                      size="small"
                      style={{ backgroundColor: verdictColor(c.label), color: "white", marginRight: 8 }}
                    />
                    <a href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}</a>
                    <PassageText>"{c.passage}"</PassageText>
                    {c.reasoning && (
                      <Typography variant="caption" color="textSecondary">{c.reasoning}</Typography>
                    )}
                  </CitationBox>
                ))}
              </>
            )}
          </Grid>
        )}
      </Grid>
    </div>
  );
}
