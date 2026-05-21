import React from "react";
import { useSelector, useDispatch } from "react-redux";
import {
  Grid, TextField, IconButton, InputAdornment, Button,
  FormControl, MenuItem, Select, InputLabel,
  Collapse, Link as MuiLink,
} from "@mui/material";
import { styled } from "@mui/material/styles";
import SearchIcon from "@mui/icons-material/Search";
import type { RootState } from "~/store/reducers/rootReducer";
import type { AppDispatch } from "~/store";
import { checkFact } from "~/store/actions/factcheckActions";
import type { PreferSource } from "~/types/api";

const InputWrapper = styled(FormControl)(({ theme }) => ({
  margin: theme.spacing(1),
}));

const ButtonRow = styled(Grid)(({ theme }) => ({
  marginTop: theme.spacing(1),
  marginRight: theme.spacing(1),
}));

const AdvancedToggle = styled(MuiLink)(({ theme }) => ({
  marginTop: theme.spacing(1),
  marginLeft: theme.spacing(2),
  marginBottom: theme.spacing(3),
  cursor: "pointer",
}));

export default function SearchInput() {
  const dispatch       = useDispatch<AppDispatch>();
  const fetchingAnswer = useSelector((state: RootState) => state.factcheck.fetchingAnswer);

  const [claim, setClaim]               = React.useState("");
  const [preferSource, setPreferSource] = React.useState<PreferSource>("auto");
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const [error, setError]               = React.useState("");

  const submit = (event: React.SyntheticEvent): void => {
    event.preventDefault();
    if (!claim.trim()) { 
      setError("Please enter a claim"); 
      return;
    }
    setError("");
    dispatch(checkFact({ 
      claim: claim.trim(), 
      prefer_source: preferSource 
    }));
  };

  return (
    <InputWrapper fullWidth variant="filled">
      <Grid container direction="row" alignItems="stretch" spacing={2}>
        <Grid item xs={18}>
          <TextField
            label="Enter a claim to verify"
            type="search"
            variant="outlined"
            fullWidth
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit(e)}
            error={Boolean(error)}
            helperText={error || "An AI agent will search the web and cite its evidence."}
            FormHelperTextProps={{ sx: { fontSize: "0.90rem" } }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={submit}>
                    <SearchIcon />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        </Grid>

        <ButtonRow item xs={12}>
          <Button type="submit" variant="contained" color="primary" onClick={submit} disabled={fetchingAnswer}>
            {fetchingAnswer ? "Verifying..." : "Verify"}
          </Button>
          <AdvancedToggle
            onClick={() => setAdvancedOpen(!advancedOpen)}
          >
            {advancedOpen ? "Hide options" : "Advanced"}
          </AdvancedToggle>
        </ButtonRow>

        <Grid item xs={12}>
          <Collapse in={advancedOpen}>
            <FormControl variant="outlined" size="small" style={{ minWidth: 220 }}>
              <InputLabel id="prefer-source-label">Preferred source</InputLabel>
              <Select
                labelId="prefer-source-label"
                value={preferSource}
                onChange={(e) => setPreferSource(e.target.value as PreferSource)}
                label="Preferred source"
              >
                <MenuItem value="auto">Auto (agent decides)</MenuItem>
                <MenuItem value="wiki">Wikipedia</MenuItem>
                <MenuItem value="web">Web (Google + Bing)</MenuItem>
              </Select>
            </FormControl>
          </Collapse>
        </Grid>
      </Grid>
    </InputWrapper>
  );
}
