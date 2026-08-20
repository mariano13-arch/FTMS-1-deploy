import { FormEvent, useEffect, useRef, useState } from "react";
import { useHistory, useLocation } from "react-router-dom";
import { ApiError } from "../../services/api";
import { setupDriverPassword } from "../../services/driverSetup";

const incompleteLinkMessage =
  "This setup link is incomplete or invalid. Please request a new invitation from your FTMS administrator.";
const rejectedLinkMessage = "This setup link is invalid, expired, or has already been used.";

function stringsFrom(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(stringsFrom);
  return [];
}

type SetupFailure =
  | { kind: "invalid-link" }
  | { kind: "messages"; messages: string[] };

function setupFailure(reason: unknown): SetupFailure {
  if (!(reason instanceof ApiError) || !reason.body || typeof reason.body !== "object") {
    return { kind: "messages", messages: ["Unable to set your password. Please try again."] };
  }
  const body = reason.body as Record<string, unknown>;
  if (
    reason.status === 400 &&
    body.detail === "Invalid or expired setup link."
  ) {
    return { kind: "invalid-link" };
  }
  if (typeof body.detail === "string") {
    return { kind: "messages", messages: [body.detail] };
  }
  const messages = Array.from(new Set(
    Object.values(body)
      .flatMap(stringsFrom)
      .map((message) => message.trim())
      .filter(Boolean),
  )).slice(0, 10);
  return {
    kind: "messages",
    messages: messages.length
      ? messages
      : ["Unable to set your password. Please try again."],
  };
}

export default function SetupPasswordPage() {
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
  const [linkRejected, setLinkRejected] = useState(false);
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
      await setupDriverPassword(
        { uid, token, new_password: newPassword, confirm_password: confirmPassword },
        requestController.signal,
      );
      if (!mounted.current) return;
      setNewPassword("");
      setConfirmPassword("");
      setSucceeded(true);
      history.replace("/setup-password");
    } catch (reason) {
      if (!mounted.current || (reason instanceof DOMException && reason.name === "AbortError")) return;
      const failure = setupFailure(reason);
      if (failure.kind === "invalid-link") {
        setLinkRejected(true);
        setNewPassword("");
        setConfirmPassword("");
      } else {
        setErrors(failure.messages);
      }
    } finally {
      inFlight.current = false;
      controller.current = null;
      if (mounted.current) setBusy(false);
    }
  };

  return <main className="setup-password-page"><section className="setup-password-card" aria-labelledby="setup-password-title">
    <div className="login-brand"><span className="brand__mark">FT<br />MS</span><div><strong>Fleet & Transport</strong><small>Management System</small></div></div>
    {succeeded ? <div className="setup-password-state setup-password-state--success" role="status">
      <p className="eyebrow">Driver account ready</p>
      <h1 id="setup-password-title">Password set successfully</h1>
      <p>Your FTMS Driver account is ready. You can now sign in to FTMS Driver Mobile using your driver username and new password.</p>
    </div> : !hasSetupLink || linkRejected ? <div className="setup-password-state" role="alert">
      <p className="eyebrow">Driver account setup</p>
      <h1 id="setup-password-title">Setup link unavailable</h1>
      <p>{linkRejected ? rejectedLinkMessage : incompleteLinkMessage}</p>
      {linkRejected && <p>Contact your FTMS administrator for a new account setup invitation.</p>}
    </div> : <>
      <p className="eyebrow">Driver account setup</p>
      <h1 id="setup-password-title">Set up your Driver account</h1>
      <p className="setup-password-intro">Choose a password before signing in to FTMS Driver Mobile.</p>
      <form onSubmit={submit} noValidate>
        <label>New password<input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} disabled={busy} /></label>
        <label>Confirm password<input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} disabled={busy} /></label>
        {errors.length > 0 && <div className="form-error-summary message message--error" role="alert"><strong>Unable to set password</strong><ul>{errors.map((message) => <li key={message}>{message}</li>)}</ul></div>}
        <button disabled={busy}>{busy ? "Setting password…" : "Set Password"}</button>
      </form>
    </>}
  </section></main>;
}
