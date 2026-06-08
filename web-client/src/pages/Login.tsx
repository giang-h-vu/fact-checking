import { Avatar, Divider, Link, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import factCheckImage from "~/assets/fact-check.png";
import {
  BrandRing,
  Dot,
  DotRow,
  enter,
  GlassCard,
  GoogleButton,
  LoginBackdrop,
  OrbBottomLeft,
  OrbTopRight,
} from "~/pages/Login.styles";

// OAuth uses a server-side redirect flow: the button sends the browser to the
// backend, which performs the Google handshake, sets session cookies, and
// redirects back to the frontend.
const handleGoogleSignIn = () => {
  window.location.href = "/api/v1/auth/google/login";
};

/** Official multicolour Google "G". Kept in brand colours per Google's
 *  identity guidelines */
const GoogleMark = () => (
  <svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true" focusable="false">
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
  </svg>
);

export default function Login() {
  const { palette } = useTheme();
  const { verdict, brand, text } = palette;

  return (
    <LoginBackdrop>
      <OrbTopRight aria-hidden />
      <OrbBottomLeft aria-hidden />

      <GlassCard elevation={0}>
        <BrandRing sx={enter(80)}>
          <Avatar src={factCheckImage} alt="" sx={{ width: "3.25rem", height: "3.25rem" }} />
        </BrandRing>

        <Typography variant="h4" sx={{ ...enter(160), fontWeight: 600, color: text.primary }}>
          Fact-Checking Tool
        </Typography>
        <Typography variant="body2" sx={{ ...enter(220), mt: 1, color: text.secondary }}>
          Sign in to verify claims and revisit your past checks.
        </Typography>

        <DotRow sx={enter(300)} aria-hidden>
          {[verdict.SUPPORTED.main, verdict.REFUTED.main, verdict.NOT_ENOUGH_INFO.main].map((c) => (
            <Dot key={c} sx={{ bgcolor: c }} />
          ))}
        </DotRow>

        <GoogleButton
          onClick={handleGoogleSignIn}
          fullWidth
          variant="outlined"
          startIcon={<GoogleMark />}
          sx={enter(380)}
        >
          Continue with Google
        </GoogleButton>

        <Divider sx={{ ...enter(460), my: 2.5, color: text.secondary, fontSize: "0.75rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
          Secure sign-in
        </Divider>

        <Typography variant="caption" sx={{ ...enter(520), display: "block", color: text.secondary }}>
          By continuing you agree to our{" "}
          <Link href="/about" underline="hover" sx={{ color: brand.dark, fontWeight: 500 }}>Terms</Link>
          {" "}and{" "}
          <Link href="/about" underline="hover" sx={{ color: brand.dark, fontWeight: 500 }}>Privacy Policy</Link>.
        </Typography>
      </GlassCard>
    </LoginBackdrop>
  );
}
