import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import { ApiError } from "../../services/api";
import { setupStaffPassword } from "./api";
import "./StaffSetupPasswordPage.css";

const incompleteLinkMessage = "This setup link is incomplete or invalid. Request a new invitation from your FTMS administrator.";
const rejectedLinkMessage = "This setup link is invalid, expired, inactive, or has already been used.";

function stringsFrom(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(stringsFrom);
  return [];
}

function setupFailure(reason: unknown) {
  if (!(reason instanceof ApiError) || !reason.body || typeof reason.body !== "object") {
    return { rejected: false, messages: ["Unable to set your password. Please try again."] };
  }
  const body = reason.body as Record<string, unknown>;
  if (reason.status === 400 && body.detail === "Invalid or expired setup link.") {
    return { rejected: true, messages: [] };
  }
  const messages = typeof body.detail === "string"
    ? [body.detail]
    : Array.from(new Set(Object.values(body).flatMap(stringsFrom).filter(Boolean))).slice(0, 10);
  return { rejected: false, messages: messages.length ? messages : ["Unable to set your password. Please try again."] };
}

export default function StaffSetupPasswordPage() {
  const history = useHistory();
  const location = useLocation();
  const parameters = new URLSearchParams(location.search);
  const uid = parameters.get("uid")?.trim() ?? "";
  const token = parameters.get("token")?.trim() ?? "";
  const hasSetupLink = Boolean(uid && token);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [rejected, setRejected] = useState(false);
  const [succeeded, setSucceeded] = useState(false);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (inFlight.current || !hasSetupLink) return;
    if (!newPassword || !confirmPassword) {
      setErrors(["Enter and confirm your new password."]);
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrors(["Passwords do not match."]);
      return;
    }

    inFlight.current = true;
    setBusy(true);
    setErrors([]);
    const requestController = new AbortController();
    controller.current = requestController;
    try {
      await setupStaffPassword({ uid, token, new_password: newPassword, confirm_password: confirmPassword }, requestController.signal);
      if (!mounted.current) return;
      setNewPassword("");
      setConfirmPassword("");
      setSucceeded(true);
      history.replace("/setup-staff-password");
    } catch (reason) {
      if (!mounted.current || (reason instanceof DOMException && reason.name === "AbortError")) return;
      const failure = setupFailure(reason);
      if (failure.rejected) {
        setRejected(true);
        setNewPassword("");
        setConfirmPassword("");
      } else setErrors(failure.messages);
    } finally {
      inFlight.current = false;
      controller.current = null;
      if (mounted.current) setBusy(false);
    }
  };

  return <main className="staff-setup-page"><section className="staff-setup-card" aria-labelledby="staff-setup-title">
    <div className="staff-setup-brand"><span>FT<br />MS</span><div><strong>Fleet &amp; Transport</strong><small>Management System</small></div></div>
    {succeeded ? <div className="staff-setup-state staff-setup-state--success" role="status">
      <p className="staff-setup-kicker">Staff account ready</p>
      <h1 id="staff-setup-title">Password set successfully</h1>
      <p>Your FTMS staff account is ready. Sign in using your staff username and new password.</p>
      <Link to="/login">Go to Staff Login</Link>
    </div> : !hasSetupLink || rejected ? <div className="staff-setup-state" role="alert">
      <p className="staff-setup-kicker">Staff account setup</p>
      <h1 id="staff-setup-title">Setup link unavailable</h1>
      <p>{rejected ? rejectedLinkMessage : incompleteLinkMessage}</p>
      {rejected && <p>Contact your FTMS administrator for a new setup invitation.</p>}
    </div> : <>
      <p className="staff-setup-kicker">Staff account setup</p>
      <h1 id="staff-setup-title">Set up your staff account</h1>
      <p className="staff-setup-intro">Choose a secure password before signing in to FTMS.</p>
      <form onSubmit={submit} noValidate>
        <label>New Password<input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} disabled={busy} /></label>
        <label>Confirm Password<input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} disabled={busy} /></label>
        {errors.length > 0 && <div className="staff-setup-error" role="alert"><strong>Unable to set password</strong><ul>{errors.map((message) => <li key={message}>{message}</li>)}</ul></div>}
        <button disabled={busy}>{busy ? "Setting password…" : "Set Password"}</button>
      </form>
    </>}
  </section></main>;
}
