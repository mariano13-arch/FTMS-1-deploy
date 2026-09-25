import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, Redirect, useHistory, useLocation } from "react-router-dom";
import { LogIn, Loader2, User, Lock, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useAuth } from "../../contexts/AuthContext";
import { safeInternalPath } from "../../services/navigation";
import AuthLayout from "../../layouts/AuthLayout";
import { isLoginTemporarilyLockedError } from "../../services/auth";
import type { TwoFactorSetup } from "../../services/auth";

function retrySeconds(error: unknown) {
  if (
    typeof error === "object" &&
    error !== null &&
    "retryAfterSeconds" in error &&
    typeof error.retryAfterSeconds === "number"
  ) return Math.max(0, Math.ceil(error.retryAfterSeconds));
  return null;
}

function lockoutMessage(seconds: number | null) {
  if (seconds === null || seconds <= 0) {
    return "Too many failed sign-in attempts. Please wait before trying again.";
  }
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `Too many failed sign-in attempts. Please try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

export default function LoginPage() {
  const {
    user, signIn, completeTwoFactor, completeRequiredMfaEnrollment,
    activateEnrolledSession, sessionMessage,
  } = useAuth();
  const history = useHistory();
  const location = useLocation();
  const [error, setError] = useState("");
  const [lockoutRemainingSeconds, setLockoutRemainingSeconds] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [recoveryMode, setRecoveryMode] = useState(false);
  const [enrollment, setEnrollment] = useState<{
    challengeToken: string; setup: TwoFactorSetup;
  } | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const mounted = useRef(false);
  const inFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (lockoutRemainingSeconds === null || lockoutRemainingSeconds <= 0) return undefined;
    const timer = window.setInterval(() => {
      setLockoutRemainingSeconds((current) => {
        if (current === null) return null;
        return Math.max(0, current - 1);
      });
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [lockoutRemainingSeconds]);

  if (user && !recoveryCodes) return <Redirect to="/transport-requests" />;

  const displayError =
    lockoutRemainingSeconds !== null && lockoutRemainingSeconds > 0
      ? lockoutMessage(lockoutRemainingSeconds)
      : error;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (inFlight.current || (lockoutRemainingSeconds !== null && lockoutRemainingSeconds > 0)) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setLockoutRemainingSeconds(null);
    const data = new FormData(event.currentTarget);
    try {
      const result = await signIn(String(data.get("username")), String(data.get("password")));
      if (result.kind === "two_factor_required") setChallengeToken(result.challengeToken);
      else if (result.kind === "mfa_enrollment_required") {
        setEnrollment({ challengeToken: result.challengeToken, setup: result.setup });
      } else history.replace(safeInternalPath((location.state as { from?: string } | null)?.from));
    } catch (signInError) {
      if (mounted.current) {
        if (isLoginTemporarilyLockedError(signInError)) {
          const seconds = retrySeconds(signInError);
          setLockoutRemainingSeconds(seconds);
          setError(lockoutMessage(seconds));
        } else {
          setError("Unable to sign in with those credentials.");
        }
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const confirmEnrollment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!enrollment || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const data = new FormData(event.currentTarget);
      setRecoveryCodes(await completeRequiredMfaEnrollment(
        enrollment.challengeToken, String(data.get("code")),
      ));
    } catch { if (mounted.current) setError("Unable to verify that authenticator code."); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const verifySecondFactor = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!challengeToken || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const data = new FormData(event.currentTarget);
      await completeTwoFactor(
        challengeToken, recoveryMode ? "recovery" : "totp", String(data.get("code")),
      );
      history.replace(safeInternalPath((location.state as { from?: string } | null)?.from));
    } catch { if (mounted.current) setError("Unable to verify that security code."); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const backToSignIn = () => { setChallengeToken(null); setRecoveryMode(false); setError(""); };

  return (
    <AuthLayout>
      <h1
        className="text-center fw-semibold mb-2"
        style={{ color: "var(--color-maroon)", fontSize: "1.25rem" }}
      >
        {recoveryCodes ? "Save Your Recovery Codes" : enrollment
          ? "Set Up Two-Factor Authentication" : challengeToken
            ? "Two-Factor Authentication" : "Sign in to FTMS"}
      </h1>
      <p
        className="text-center small mb-4"
        style={{ color: "var(--color-taupe)", fontSize: "0.875rem" }}
      >
        {recoveryCodes
          ? "Store these one-time codes securely. They will not be shown again."
          : enrollment
            ? "MFA is required for your role. Scan the QR code before continuing."
            : challengeToken
          ? "Enter the 6-digit code from your authenticator app."
          : "Sign in with the credentials given to you by your administrator."}
      </p>
      {!challengeToken && sessionMessage && (
        <div className="alert alert-warning small" role="status">{sessionMessage}</div>
      )}
      {recoveryCodes ? <div className="d-flex flex-column gap-3">
        <div className="alert alert-warning small mb-0 font-monospace" data-testid="recovery-codes">
          {recoveryCodes.join("\n")}
        </div>
        <button type="button" className="btn login-btn-charcoal" onClick={() => {
          void activateEnrolledSession().then(() => history.replace(
            safeInternalPath((location.state as { from?: string } | null)?.from),
          )).catch(() => setError("Unable to complete sign-in."));
        }}>I have saved these codes</button>
      </div> : enrollment ? <form onSubmit={confirmEnrollment} className="d-flex flex-column gap-3" noValidate>
        <div className="text-center"><div className="bg-white p-2 d-inline-block border rounded">
          <QRCodeSVG value={enrollment.setup.provisioning_uri} size={156} />
        </div></div>
        <p className="small mb-0">Manual setup key:</p>
        <code className="small text-break">{enrollment.setup.manual_setup_key}</code>
        <label htmlFor="enrollment-code" className="form-label fw-medium mb-0">Authenticator code</label>
        <input id="enrollment-code" name="code" required autoFocus autoComplete="one-time-code"
          inputMode="numeric" className="form-control login-input" placeholder="123456" />
        {error && <div className="alert alert-danger small" role="alert">{error}</div>}
        <button type="submit" disabled={busy} className="btn login-btn-charcoal">
          {busy ? "Verifying…" : "Enable MFA and continue"}
        </button>
      </form> : challengeToken ? <form onSubmit={verifySecondFactor} className="d-flex flex-column gap-3" noValidate>
        <div>
          <label htmlFor="two-factor-code" className="form-label fw-medium mb-1" style={{ color: "var(--color-charcoal)", fontSize: "0.875rem" }}>
            {recoveryMode ? "Recovery code" : "Authenticator code"}
          </label>
          <div className="position-relative"><ShieldCheck size={17} strokeWidth={2} className="position-absolute top-50 translate-middle-y pointer-events-none" style={{ left: "14px", color: "var(--color-taupe)" }} />
            <input id="two-factor-code" name="code" required autoFocus autoComplete="one-time-code" inputMode="numeric" className="form-control login-input" style={{ paddingLeft: "40px" }} placeholder={recoveryMode ? "Enter recovery code" : "123456"} />
          </div>
        </div>
        {error && <div className="alert alert-danger small mt-2" role="alert">{error}</div>}
        <button type="submit" disabled={busy} className="btn login-btn-charcoal mt-2 w-100 py-2 d-flex align-items-center justify-content-center gap-2 fw-medium" style={{ fontSize: "0.875rem" }}>
          {busy ? <Loader2 size={16} className="login-spinner-icon" /> : <ShieldCheck size={16} />}{busy ? "Verifying…" : "Verify"}
        </button>
        <button type="button" className="btn btn-link btn-sm" onClick={() => { setRecoveryMode(!recoveryMode); setError(""); }}>
          {recoveryMode ? "Use authenticator code" : "Use recovery code"}
        </button>
        <button type="button" className="btn btn-link btn-sm" onClick={backToSignIn}>Back to sign in</button>
      </form> :
      <form onSubmit={submit} className="d-flex flex-column gap-3" noValidate>
        <div>
          <label
            htmlFor="login-username"
            className="form-label fw-medium mb-1"
            style={{ color: "var(--color-charcoal)", fontSize: "0.875rem" }}
          >
            Username
          </label>
          <div className="position-relative">
            <User
              size={17}
              strokeWidth={2}
              className="position-absolute top-50 translate-middle-y pointer-events-none"
              style={{ left: "14px", color: "var(--color-taupe)" }}
            />
            <input
              id="login-username"
              type="text"
              name="username"
              required
              autoComplete="username"
              placeholder="username"
              className="form-control login-input"
              style={{ paddingLeft: "40px", paddingRight: "14px" }}
            />
          </div>
        </div>

        <div>
          <label
            htmlFor="login-password"
            className="form-label fw-medium mb-1"
            style={{ color: "var(--color-charcoal)", fontSize: "0.875rem" }}
          >
            Password
          </label>
          <div className="position-relative">
            <Lock
              size={17}
              strokeWidth={2}
              className="position-absolute top-50 translate-middle-y pointer-events-none"
              style={{ left: "14px", color: "var(--color-taupe)" }}
            />
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              name="password"
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="form-control login-input"
              style={{ paddingLeft: "40px", paddingRight: "40px" }}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="btn btn-link p-0 position-absolute top-50 translate-middle-y text-decoration-none border-0"
              style={{ right: "14px", color: "var(--color-taupe)" }}
            >
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
        </div>

        <div className="text-end" style={{ marginTop: "-0.5rem" }}>
          <Link to="/forgot-password" className="small">Forgot password?</Link>
        </div>

        {displayError && (
          <div className="alert alert-danger small mt-2" role="alert">
            {displayError}
          </div>
        )}

        <button
          type="submit"
          disabled={busy || (lockoutRemainingSeconds !== null && lockoutRemainingSeconds > 0)}
          className="btn login-btn-charcoal mt-2 w-100 py-2 d-flex align-items-center justify-content-center gap-2 fw-medium"
          style={{ fontSize: "0.875rem" }}
        >
          {busy ? (
            <Loader2 size={16} className="login-spinner-icon" />
          ) : (
            <LogIn size={16} />
          )}
          {busy ? "Signing in\u2026" : "Sign in"}
        </button>
      </form>
      }
    </AuthLayout>
  );
}
