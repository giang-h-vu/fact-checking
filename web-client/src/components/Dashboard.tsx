import { NavLink } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Avatar, Box, Button, Typography, useTheme } from '@mui/material';
import LogoutIcon from '@mui/icons-material/Logout';
import factCheckImage from '~/assets/fact-check.png';
import timeImage from '~/assets/time.png';
import workingsImage from '~/assets/workings.png';
import binocularsImage from '~/assets/binoculars.png';
import type { AppDispatch } from '~/store';
import type { RootState } from '~/store/reducers/rootReducer';
import { logout } from '~/store/actions/authActions';

export const Dashboard = () => {
  const dispatch = useDispatch<AppDispatch>();
  const user = useSelector((s: RootState) => s.auth.user);
  const { palette } = useTheme();
  const { brand, text } = palette;

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

      {user && (
        <Box sx={{ mt: "auto", p: 2, display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
          <Avatar src={user.picture ?? undefined} alt={user.name} sx={{ width: 48, height: 48 }} />
          <Typography variant="subtitle2" sx={{ color: text.primary }}>{user.name}</Typography>
          <Typography variant="caption" sx={{ color: text.secondary }}>{user.email}</Typography>
          <Button
            size="small"
            startIcon={<LogoutIcon />}
            onClick={() => dispatch(logout())}
            sx={{ mt: 1, textTransform: "none", color: brand.dark }}
          >
            Sign out
          </Button>
        </Box>
      )}
    </nav>
  );
};
