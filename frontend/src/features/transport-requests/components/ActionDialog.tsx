import { FormEvent, useState } from "react";

export type ActionDialogState = {
  action: string; title: string; description: string; confirmLabel: string;
  note: "required" | "optional" | "hidden"; context?: string;
};

export default function ActionDialog({ dialog, busy, error, close, confirm }: {
  dialog: ActionDialogState; busy: boolean; error: string; close: () => void;
  confirm: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState(""); const needsNote = dialog.note === "required";
  const submit = (event: FormEvent) => { event.preventDefault(); if (!busy && (!needsNote || note.trim())) void confirm(note.trim()); };
  return <div className="dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) close(); }}><section className="action-dialog" role="dialog" aria-modal="true" aria-labelledby="action-dialog-title"><form onSubmit={submit}><header><div><span>Confirm action</span><h2 id="action-dialog-title">{dialog.title}</h2></div><button type="button" className="dialog-close" aria-label="Close dialog" disabled={busy} onClick={close}>×</button></header><p>{dialog.description}</p>{dialog.context && <div className="dialog-context">{dialog.context}</div>}{dialog.note !== "hidden" && <label>{needsNote ? "Reason (required)" : "Note (optional)"}<textarea autoFocus rows={4} value={note} onChange={event => setNote(event.target.value)} required={needsNote} maxLength={1000} /></label>}{error && <p className="message message--error" role="alert">{error}</p>}<footer><button type="button" className="button--secondary" disabled={busy} onClick={close}>Back</button><button disabled={busy || (needsNote && !note.trim())}>{busy ? "Submitting…" : dialog.confirmLabel}</button></footer></form></section></div>;
}
