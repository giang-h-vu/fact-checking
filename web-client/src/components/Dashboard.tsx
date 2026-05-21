import { NavLink } from 'react-router-dom';
import { Typography } from '@mui/material';
import factCheckImage from '~/assets/fact-check.png';
import timeImage from '~/assets/time.png';

export const Dashboard = () => {
  return (
    <nav className="dashboard">
      <NavLink className="app-name" to="/">
        <img src={factCheckImage} alt="" />
        <Typography variant="h1">Fact-Checking Tool</Typography>
        <Typography variant="body2">Verify claims to see how true they are</Typography>
      </NavLink>
      <div className="links">
        <NavLink className="link" to="/history">
          <img src={timeImage} alt="" />
          <Typography variant="h2">Past Claims</Typography>
        </NavLink>
      </div>
    </nav>
  );
};
