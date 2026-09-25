import { FormEvent, useState } from "react";
import { createPortal } from "react-dom";

export type ActionDialogState = {
  action: string;
  title: string;
  description: string;
  confirmLabel: string;
  note: "required" | "optional" | "hidden";
  context?: string;
  dismissLabel?: string;
};

export default function ActionDialog({
  dialog,
  busy,
  error,
  close,
  confirm,
}: {
  dialog: ActionDialogState;
  busy: boolean;
  error: string;
  close: () => void;
  confirm: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const needsNote = dialog.note === "required";
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!busy && (!needsNote || note.trim())) void confirm(note.trim());
  };
  const portalRoot = document.querySelector<HTMLElement>(".app-layout") ?? document.body;
  return createPortal(
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) close();
      }}
    >
      <section
        className="action-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="action-dialog-title"
      >
        <form onSubmit={submit}>
          <header>
            <div>
              <span>Confirm action</span>
              <h2 id="action-dialog-title">{dialog.title}</h2>
            </div>
            <button
              type="button"
              className="btn-close dialog-close"
              aria-label="Close dialog"
              disabled={busy}
              onClick={close}
            >
              ×
            </button>
          </header>
          <p>{dialog.description}</p>
          {dialog.context && (
            <div className="dialog-context">{dialog.context}</div>
          )}
          {dialog.note !== "hidden" && (
            <label>
              {needsNote ? "Reason (required)" : "Note (optional)"}
              <textarea
                className="form-control"
                autoFocus
                rows={4}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                required={needsNote}
                maxLength={1000}
              />
            </label>
          )}
          {error && (
            <p
              className="message message--error alert alert-danger"
              role="alert"
            >
              {error}
            </p>
          )}
          <footer>
            <button
              type="button"
              className="btn-cancel"
              disabled={busy}
              onClick={close}
            >
              {dialog.dismissLabel ?? "Back"}
            </button>
            <button
              className="btn-confirm"
              disabled={busy || (needsNote && !note.trim())}
            >
              {busy ? "Submitting…" : dialog.confirmLabel}
            </button>
          </footer>
        </form>
      </section>
    </div>,
    portalRoot,
  );
}
