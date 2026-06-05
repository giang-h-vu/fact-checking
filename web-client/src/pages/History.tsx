import React, { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Grid, Typography } from "@mui/material";
import type { RootState } from "~/store/reducers/rootReducer";
import type { AppDispatch } from "~/store";
import type { HistoryItem } from "~/types/api";
import { getHistory } from "~/store/actions/factcheckActions";
import VerdictChip from "~/components/VerdictChip";
import { CardBox, CitationBox, PassageText, SectionDivider } from "~/components/StyledWrappers";
import { formatDateTime } from "~/utils/datetime";

export default function History() {
  const dispatch     = useDispatch<AppDispatch>();
  const claimHistory = useSelector((state: RootState) => state.factcheck.history);

  useEffect(() => {
    dispatch(getHistory());
  }, [dispatch]);

  return (
    <div className="search-and-more">
      <Grid container direction="row" alignItems="stretch" spacing={1} sx={{ mb: 2 }}>
        <Grid item xs={12} sx={{ ml: "6px" }}>
          <Typography gutterBottom variant="h2" align="center">History</Typography>
        </Grid>

        {claimHistory.length === 0 && (
          <Grid item xs={12} sx={{ ml: "6px" }}>
            <Typography color="textSecondary" align="center">
              No verifications yet. Submit a claim on the home page.
            </Typography>
          </Grid>
        )}

        <Grid item xs={12} className="previous-verifications">
          {claimHistory.map((item: HistoryItem, i: number) => (
            <CardBox key={item.id ?? i}>
              <Typography variant="caption" color="textSecondary">{formatDateTime(item.datetime)}</Typography>
              <Typography variant="h6" gutterBottom>"{item.claim}"</Typography>
              <VerdictChip verdict={item.verdict} />

              {(item.citations ?? []).map((c, j: number) => (
                <CitationBox key={j} elevation={1}>
                  <VerdictChip verdict={c.label} size="small" sx={{ mr: 1 }} />
                  <a href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}</a>
                  <PassageText>"{c.passage}"</PassageText>
                </CitationBox>
              ))}

              <SectionDivider />
            </CardBox>
          ))}
        </Grid>
      </Grid>
    </div>
  );
}
