import { FormEvent, useEffect, useRef, useState } from "react";
import { Redirect, useHistory, useLocation } from "react-router-dom";
import { LogIn, Loader2, User, Lock, Eye, EyeOff } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { safeInternalPath } from "../../services/navigation";
import AuthLayout from "../../layouts/AuthLayout";

export default function LoginPage() {
  const { user, signIn } = useAuth();
  const history = useHistory();
  const location = useLocation();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const mounted = useRef(false);
  const inFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  if (user) return <Redirect to="/transport-requests" />;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await signIn(String(data.get("username")), String(data.get("password")));
      history.replace(
        safeInternalPath((location.state as { from?: string } | null)?.from),
      );
    } catch {
      if (mounted.current)
        setError("Unable to sign in with those credentials.");
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <h1
        className="text-center fw-semibold mb-2"
        style={{ color: "var(--color-maroon)", fontSize: "1.25rem" }}
      >
        Fleet and Transport Management
      </h1>
      <p
        className="text-center small mb-4"
        style={{ color: "var(--color-taupe)", fontSize: "0.875rem" }}
      >
        Sign in with the credentials given to you by your administrator.
      </p>

      <form onSubmit={submit} className="d-flex flex-column gap-3" noValidate>
        <div>
          <label
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
              type="text"
              name="username"
              required
              autoComplete="username"
              placeholder="you@hotelname.com"
              className="form-control login-input"
              style={{ paddingLeft: "40px", paddingRight: "14px" }}
            />
          </div>
        </div>

        <div>
          <label
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

        {error && (
          <div className="alert alert-danger small mt-2" role="alert">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
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
    </AuthLayout>
  );
}
