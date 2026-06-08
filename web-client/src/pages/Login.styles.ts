import { Box, Button, Paper } from "@mui/material";
import { styled } from "@mui/material/styles";
import { keyframes } from "@mui/system";

// Entrance: card children fade + rise. Drift: the decorative background orbs.
const riseIn = keyframes`
  from { opacity: 0; transform: translateY(0.75rem); }
  to   { opacity: 1; transform: translateY(0); }
`;

const orbDrift = keyframes`
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-1.25rem); }
`;

// Staggered entrance: spread onto each card child with an increasing delay.
// Honours prefers-reduced-motion by skipping the animation entirely.
export const enter = (delayMs: number) => ({
  opacity: 0,
  animation: `${riseIn} 600ms cubic-bezier(0.4, 0, 0.2, 1) ${delayMs}ms forwards`,
  "@media (prefers-reduced-motion: reduce)": { animation: "none", opacity: 1 },
});

// Full-screen frosted backdrop with a soft brand glow behind the card.
export const LoginBackdrop = styled(Box)(({ theme }) => ({
  position: "relative",
  minHeight: "100vh",
  width: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: theme.spacing(4),
  overflow: "hidden",
  background: "linear-gradient(to right top, #daf3f6, #e6edee)",
  "&::before": {
    content: '""',
    position: "absolute",
    width: "42rem",
    height: "42rem",
    borderRadius: "50%",
    background: `radial-gradient(circle, ${theme.palette.brand.main}2e, transparent 60%)`,
    pointerEvents: "none",
  },
}));

const orbBase = {
  position: "absolute" as const,
  borderRadius: "50%",
  pointerEvents: "none" as const,
  background: "linear-gradient(to right top, rgba(255,255,255,0.9), rgba(255,255,255,0.3))",
};

export const OrbTopRight = styled(Box)({
  ...orbBase,
  width: "12rem",
  height: "12rem",
  top: "8%",
  right: "10%",
  animation: `${orbDrift} 14s ease-in-out infinite`,
});

export const OrbBottomLeft = styled(Box)({
  ...orbBase,
  width: "9rem",
  height: "9rem",
  left: "8%",
  bottom: "10%",
  animation: `${orbDrift} 18s ease-in-out infinite reverse`,
});

// Glass card with the teal→deep-teal accent bar across the top.
export const GlassCard = styled(Paper)(({ theme }) => ({
  position: "relative",
  zIndex: 2,
  width: "min(92%, 25rem)",
  padding: theme.spacing(5.5, 5, 4),
  borderRadius: "1.25rem",
  textAlign: "center",
  overflow: "hidden",
  background: "linear-gradient(to top right, rgba(255,255,255,0.85), rgba(255,255,255,0.45))",
  backdropFilter: "blur(2rem)",
  border: `1px solid ${theme.palette.brand.main}2e`,
  boxShadow: "0 1.5rem 3.5rem rgba(23,43,77,0.14)",
  "&::before": {
    content: '""',
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: "0.3rem",
    background: `linear-gradient(to right, ${theme.palette.brand.main}, ${theme.palette.brand.dark})`,
  },
}));

// Tinted ring around the brand avatar.
export const BrandRing = styled(Box)(({ theme }) => ({
  width: "5.5rem",
  height: "5.5rem",
  margin: theme.spacing(0, "auto", 2),
  borderRadius: "50%",
  display: "grid",
  placeItems: "center",
  background: `${theme.palette.brand.main}14`,
  border: `2px solid ${theme.palette.brand.main}59`,
  boxShadow: `0 0.5rem 1.25rem ${theme.palette.brand.main}2e`,
}));

// Verdict-colour dots row beneath the heading.
export const DotRow = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(1),
  justifyContent: "center",
  margin: theme.spacing(3, 0),
}));

export const Dot = styled(Box)({
  width: "0.5rem",
  height: "0.5rem",
  borderRadius: "50%",
  opacity: 0.85,
});

// White Google button that lifts and gains a teal halo on hover.
export const GoogleButton = styled(Button)(({ theme }) => ({
  paddingTop: theme.spacing(1.25),
  paddingBottom: theme.spacing(1.25),
  borderRadius: "0.75rem",
  textTransform: "none",
  fontSize: "0.95rem",
  fontWeight: 500,
  color: theme.palette.text.primary,
  backgroundColor: theme.palette.common.white,
  borderColor: "rgba(23,43,77,0.12)",
  boxShadow: "0 0.25rem 0.75rem rgba(23,43,77,0.06)",
  transition: theme.transitions.create(["transform", "box-shadow", "border-color"], {
    duration: 300,
  }),
  "&:hover": {
    backgroundColor: theme.palette.common.white,
    transform: "translateY(-2px)",
    borderColor: `${theme.palette.brand.main}80`,
    boxShadow: `0 0.75rem 1.5rem ${theme.palette.brand.main}33`,
  },
}));
