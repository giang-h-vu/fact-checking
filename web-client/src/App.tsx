import React from "react";
import "./App.css";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { Box, CircularProgress, Paper } from "@mui/material";
import { useDispatch, useSelector } from "react-redux";
import Home from "~/pages/Home";
import theme from "~/theme/index";
import { Dashboard } from "~/components/Dashboard";
import { HowItWorks } from "~/pages/HowItWorks";
import History from "~/pages/History";
import Login from "~/pages/Login";
import type { AppDispatch } from "~/store";
import type { RootState } from "~/store/reducers/rootReducer";
import { fetchMe } from "~/store/actions/authActions";

// The app shell. Login renders full-screen on its
// own background, outside this shell.
const AppShell = () => (
  <>
    <main>
      <section className="glass">
        <Dashboard />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/history" element={<History />} />
          <Route path="/about" element={<HowItWorks />} />
        </Routes>
      </section>
    </main>
    <div className="circle1"></div>
    <div className="circle2"></div>
  </>
);

// Gate the app shell behind authentication.
const PrivateRoute = () => {
  const status = useSelector((s: RootState) => s.auth.status);
  if (status === "loading") {
    return (
      <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <CircularProgress />
      </Box>
    );
  }
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return <AppShell />;
};

function App() {
  const dispatch = useDispatch<AppDispatch>();

  React.useEffect(() => {
    dispatch(fetchMe());
  }, [dispatch]);

  return (
    <ThemeProvider theme={theme}>
      <Paper>
        <div className="App">
          <Router>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/*" element={<PrivateRoute />} />
            </Routes>
          </Router>
        </div>
      </Paper>
    </ThemeProvider>
  );
}

export default App;
