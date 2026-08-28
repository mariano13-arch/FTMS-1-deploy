import React, { useCallback, useEffect, useRef } from "react";
import { AlertTriangle, Trash2, Info } from "lucide-react";

type ConfirmModalProps = {
  show: boolean;
  title: string;
  message: string | React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "warning" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
};

const variantIcons = {
  danger: Trash2,
  warning: AlertTriangle,
  primary: Info,
} as const;

export default function ConfirmModal({
  show,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "primary",
  onConfirm,
  onCancel,
  loading = false,
}: ConfirmModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (show) {
      previousFocus.current = document.activeElement as HTMLElement;
      setTimeout(() => confirmBtnRef.current?.focus(), 50);
    } else if (previousFocus.current) {
      previousFocus.current.focus();
    }
  }, [show]);

  useEffect(() => {
    if (!show) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) {
        e.stopPropagation();
        onCancel();
        return;
      }

      if (e.key === "Enter" && !loading) {
        e.preventDefault();
        onConfirm();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled])"
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [show, loading, onCancel, onConfirm]);

  const handleBackdropMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget && !loading) {
        onCancel();
      }
    },
    [loading, onCancel]
  );

  if (!show) return null;

  const Icon = variantIcons[variant];

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={handleBackdropMouseDown}
    >
      <div
        className={`confirm-modal confirm-modal--${variant}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        ref={dialogRef}
      >
        <header>
          <div className="confirm-modal__icon-row">
            <span className={`confirm-modal__icon confirm-modal__icon--${variant}`}>
              <Icon size={18} />
            </span>
            <span className="confirm-modal__title-label">Confirm action</span>
          </div>
          <h2 id="confirm-modal-title">{title}</h2>
        </header>
        <div className="confirm-modal__body">
          {typeof message === "string" ? <p>{message}</p> : message}
        </div>
        <footer>
          <button
            type="button"
            className="btn-cancel"
            disabled={loading}
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button
            type="button"
            ref={confirmBtnRef}
            className={`btn confirm-modal__confirm-btn confirm-modal__confirm-btn--${variant}`}
            disabled={loading}
            onClick={onConfirm}
          >
            {loading && <span className="confirm-modal__spinner login-spinner-icon" />}
            {loading ? "Processing…" : confirmText}
          </button>
        </footer>
      </div>
    </div>
  );
}
