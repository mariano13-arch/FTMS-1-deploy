import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import AuthLayout from "../../layouts/AuthLayout";
import { requestPasswordReset } from "../../services/auth";

const genericMessage = "If an eligible account matches that email, a password reset link has been sent.";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { await requestPasswordReset(email); setSubmitted(true); }
    catch { setError("Unable to submit the request. Please try again later."); }
    finally { setBusy(false); }
  };
  return <AuthLayout>
    <h1 className="text-center fw-semibold mb-2" style={{ color: "var(--color-maroon)", fontSize: "1.25rem" }}>Reset your password</h1>
    {submitted ? <div className="alert alert-success small" role="status">{genericMessage}</div> : <>
      <p className="text-center small mb-4">Enter your FTMS staff email address.</p>
      <form onSubmit={submit} className="d-flex flex-column gap-3">
        <label className="form-label small">Email address<input aria-label="Email address" type="email" autoComplete="email" required className="form-control mt-1" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        {error && <div className="alert alert-danger small" role="alert">{error}</div>}
        <button className="btn login-btn-charcoal" disabled={busy}>{busy ? "Submitting…" : "Send reset link"}</button>
      </form>
    </>}
    <div className="text-center mt-3"><Link to="/login" className="small">Back to sign in</Link></div>
  </AuthLayout>;
}
