import React from 'react';
import './App.css';
import { BrowserRouter as Router, Route, Switch } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { Paper } from "@mui/material";
import Home from '~/pages/Home';
import theme from '~/theme/index';
import { Dashboard } from '~/components/Dashboard';
import { HowItWorks } from '~/pages/HowItWorks';
import History from '~/pages/History';

function App() {
  return (
    <ThemeProvider theme={theme}>
      <Paper>
        <div className="App">
          <main>
            <section className="glass">
              <Router>
                <Dashboard />
                <Switch>
                  <Route exact path="/" component={Home} />
                  <Route path="/history" component={History} />
                  <Route path="/workings" component={HowItWorks} />
                </Switch>
                </Router>
            </section>
          </main>
          <div className="circle1"></div>
          <div className="circle2"></div>
        </div>
      </Paper>
    </ThemeProvider>
  );
}

export default App;
