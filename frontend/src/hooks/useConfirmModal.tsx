import { useCallback, useRef, useState } from "react";
import type { ReactNode } from "react";
import ConfirmModal from "../components/common/ConfirmModal";

type ConfirmOptions = {
  title: string;
  message: string | ReactNode;
  variant?: "danger" | "warning" | "primary";
  confirmText?: string;
  cancelText?: string;
};

type PendingConfirm = ConfirmOptions & {
  resolve: (value: boolean) => void;
};

export function useConfirmModal() {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [loading, setLoading] = useState(false);
  const resolveRef = useRef<(value: boolean) => void>(() => {});

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      setPending({ ...options, resolve });
      setLoading(false);
    });
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!pending || loading) return;
    setLoading(true);
    resolveRef.current(true);
    setPending(null);
    setLoading(false);
  }, [pending, loading]);

  const handleCancel = useCallback(() => {
    if (loading) return;
    resolveRef.current(false);
    setPending(null);
    setLoading(false);
  }, [loading]);

  const ConfirmModalComponent = pending ? (
    <ConfirmModal
      show
      title={pending.title}
      message={pending.message}
      variant={pending.variant}
      confirmText={pending.confirmText}
      cancelText={pending.cancelText}
      loading={loading}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  ) : null;

  return { confirm, ConfirmModalComponent };
}
