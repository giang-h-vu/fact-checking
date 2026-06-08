import React, { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  Box, Dialog, DialogContent, DialogTitle,
  Grid, IconButton, Typography,
  useTheme,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import type { RootState } from "~/store/reducers/rootReducer";
import type { AppDispatch } from "~/store";
import type { Citation, HistoryItem } from "~/types/api";
import { getHistory } from "~/store/actions/factcheckActions";
import VerdictChip from "~/components/VerdictChip";
import { CardBox, CitationBox, PassageText, SectionDivider } from "~/components/StyledWrappers";
import { formatDateTime } from "~/utils/datetime";
import { verdictLabel } from "~/utils/verdict";


function dialogLeftFromGrid(el: HTMLDivElement | null): number {
  const GRID_SPACING_PX = 24;  
  if (!el){
    return 0;
  }
  return Math.max(0, el.getBoundingClientRect().left - GRID_SPACING_PX);
}

export default function History() {
  const dispatch     = useDispatch<AppDispatch>();
  const claimHistory = useSelector((state: RootState) => state.factcheck.history);
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [gridOffsetLeft, setGridOffsetLeft] = useState(0);
  const gridRef = React.useRef<HTMLDivElement>(null);
  const { palette } = useTheme();


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
            <Typography color={palette.text.secondary} align="center">
              No verifications yet. Submit a claim on the home page.
            </Typography>
          </Grid>
        )}

        <Grid item xs={12} className="previous-verifications" ref={gridRef}>
          {claimHistory.map((item: HistoryItem, i: number) => (
            <CardBox
              key={item.id ?? i}
              onClick={() => {
                setGridOffsetLeft(dialogLeftFromGrid(gridRef.current));
                setSelected(item);
              }}
              sx={{ cursor: "pointer", "&:hover": { boxShadow: 4 } }}
            >
              <Box sx={{ minHeight: "12rem", maxHeight: "18rem", overflowY: "auto" }}>
                <Typography variant="caption" color={palette.text.secondary}>{formatDateTime(item.datetime)}</Typography>
                <Typography variant="h6" gutterBottom>"{item.claim}"</Typography>
                <VerdictChip verdict={item.verdict} />

                {(() => {
                  const citations = item.citations ?? [];
                  return citations.length === 0
                    ? <Typography variant="body2" color={palette.text.secondary} sx={{ mt: 1 }}>No evidence found.</Typography>
                    : citations.map((c, j) => (
                      <CitationBox key={j} elevation={1}>
                        <VerdictChip verdict={c.label} size="small" sx={{ mr: 1 }} />
                        <a href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}</a>
                        <PassageText>"{c.passage}"</PassageText>
                        <SectionDivider />
                        {c.reasoning && (
                          <Typography variant="caption" color={palette.text.secondary}>{c.reasoning}</Typography>
                        )}
                      </CitationBox>
                    ));
                })()}
              </Box>
            </CardBox>
          ))}
        </Grid>
      </Grid>

      <Dialog
        open={selected !== null}
        onClose={() => setSelected(null)}
        maxWidth={false}
        sx={{ "& .MuiDialog-container": { justifyContent: "flex-start", paddingLeft: `${gridOffsetLeft}px` } }}
        PaperProps={{ sx: { width: "80rem", maxWidth: `calc(100vw - ${gridOffsetLeft}px)` } }}
      >
        <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="caption" color={palette.text.secondary}>
            {selected && formatDateTime(selected.datetime)}
          </Typography>
          <IconButton size="small" onClick={() => setSelected(null)}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>

        {selected && (
          <DialogContent>
            <CardBox>
              <Typography variant="subtitle2" color={palette.text.secondary}>Claim</Typography>
              <Typography variant="body1" gutterBottom>"{selected.claim}"</Typography>
              <VerdictChip verdict={selected.verdict} label={`Verdict: ${verdictLabel(selected.verdict)}`} sx={{ fontSize: "1rem" }} />
            </CardBox>

            {(selected.citations ?? []).length > 0 && (
              <>
                <Typography variant="h6" sx={{ ml: "6px" }}>Citations</Typography>
                {(selected.citations ?? []).map((c: Citation, i: number) => (
                  <CitationBox key={i}>
                    <VerdictChip verdict={c.label} size="small" sx={{ mr: 1 }} />
                    <a href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}</a>
                    <PassageText>"{c.passage}"</PassageText>
                    {c.reasoning && (
                      <Typography variant="caption" color={palette.text.secondary}>{c.reasoning}</Typography>
                    )}
                  </CitationBox>
                ))}
              </>
            )}
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
