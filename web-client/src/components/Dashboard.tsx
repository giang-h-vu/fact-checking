import { NavLink } from 'react-router-dom';
import { Typography } from '@mui/material';
import factCheckImage from '~/assets/fact-check.png';
import timeImage from '~/assets/time.png';
import workingsImage from '~/assets/workings.png';
import binocularsImage from '~/assets/binoculars.png';

export const Dashboard = () => {
  return (
    <nav className="dashboard">
      <div className="app-name">
        <img src={factCheckImage} alt="" />
        <Typography variant="h1">Fact-Checking Tool</Typography>
        <Typography variant="body2">Evaluate statements to determine their validity.</Typography>
      </div>
      <div className="links">
        <NavLink className="link" exact to="/">
          <img src={binocularsImage} alt="Fact Checking" />
          <Typography variant="h2">Fact Check</Typography>
        </NavLink>
        <NavLink className="link" to="/history">
          <img src={timeImage} alt="History" />
          <Typography variant="h2">Past Claims</Typography>
        </NavLink>
        <NavLink className="link" to="/about">
          <img src={workingsImage} alt="How It Works" />
          <Typography variant="h2">How It Works</Typography>
        </NavLink>
      </div>
    </nav>
  );
};
