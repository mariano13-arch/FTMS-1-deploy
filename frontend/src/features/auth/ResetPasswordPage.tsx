import { FormEvent, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import AuthLayout from "../../layouts/AuthLayout";
import { ApiError } from "../../services/api";
import { resetPassword } from "../../services/auth";

function messages(reason: unknown) {
  if (!(reason instanceof ApiError) || !reason.body || typeof reason.body !== "object") return ["Unable to reset your password."];
  const body = reason.body as Record<string, unknown>;
  if (body.detail === "Invalid or expired password reset link.") return [String(body.detail)];
  return Object.values(body).flatMap((value) => Array.isArray(value) ? value.map(String) : [String(value)]);
}

export default function ResetPasswordPage() {
  const location = useLocation(); const history = useHistory();
  const params = new URLSearchParams(location.search);
  const uid = params.get("uid") ?? ""; const token = params.get("token") ?? "";
  const [newPassword, setNewPassword] = useState(""); const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<string[]>([]); const [busy, setBusy] = useState(false); const [done, setDone] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmation) { setErrors(["Passwords do not match."]); return; }
    setBusy(true); setErrors([]);
    try { await resetPassword(uid, token, newPassword, confirmation); setDone(true); history.replace("/reset-password"); }
    catch (reason) { setErrors(messages(reason)); }
    finally { setBusy(false); }
  };
  const invalid = !uid || !token;
  return <AuthLayout>
    <h1 className="text-center fw-semibold mb-2" style={{ color: "var(--color-maroon)", fontSize: "1.25rem" }}>Choose a new password</h1>
    {done ? <div className="alert alert-success small" role="status">Password changed. Sign in with your new password.</div> : invalid ? <div className="alert alert-danger small" role="alert">This password reset link is incomplete or invalid.</div> : <form onSubmit={submit} className="d-flex flex-column gap-3">
      <p className="small mb-0">Use a strong password that is not common or entirely numeric.</p>
      <label className="form-label small">New password<input aria-label="New password" type="password" autoComplete="new-password" required className="form-control mt-1" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
      <label className="form-label small">Confirm password<input aria-label="Confirm password" type="password" autoComplete="new-password" required className="form-control mt-1" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
      {errors.length > 0 && <div className="alert alert-danger small" role="alert"><ul className="mb-0">{errors.map((error) => <li key={error}>{error}</li>)}</ul></div>}
      <button className="btn login-btn-charcoal" disabled={busy}>{busy ? "Resetting…" : "Reset password"}</button>
    </form>}
    <div className="text-center mt-3"><Link to="/login" className="small">Back to sign in</Link></div>
  </AuthLayout>;
}
