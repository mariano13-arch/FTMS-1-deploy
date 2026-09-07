import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { ApiError } from '@/services/api';
import {
  bootstrapCsrf,
  getCurrentStaff,
  signInStaff,
  signOutStaff,
  verifyStaffSecondFactor,
} from '@/services/staffAuth';
import type { StaffIdentity } from '@/types';

type ContextValue = {
  staff: StaffIdentity | null;
  challengeToken: string | null;
  isBootstrapping: boolean;
  isSubmitting: boolean;
  error: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  verifySecondFactor: (method: 'totp' | 'recovery', code: string) => Promise<void>;
  cancelSecondFactor: () => void;
  signOut: () => Promise<void>;
};

const StaffAuthContext = createContext<ContextValue | null>(null);

function message(error: unknown) {
  return error instanceof ApiError ? error.message : 'An unexpected authentication error occurred.';
}

export function StaffAuthProvider({ children }: PropsWithChildren) {
  const [staff, setStaff] = useState<StaffIdentity | null>(null);
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function bootstrap() {
      try {
        await bootstrapCsrf(controller.signal);
        setStaff(await getCurrentStaff(controller.signal));
      } catch (bootstrapError) {
        if (bootstrapError instanceof Error && bootstrapError.name === 'AbortError') return;
        setStaff(null);
        if (!(bootstrapError instanceof ApiError && bootstrapError.status === 401)) {
          setError(message(bootstrapError));
        }
      } finally {
        if (!controller.signal.aborted) setIsBootstrapping(false);
      }
    }
    void bootstrap();
    return () => controller.abort();
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await signInStaff(username, password);
      setChallengeToken(result.challengeToken ?? null);
      setStaff(result.staff ?? null);
    } catch (signInError) {
      setError(message(signInError));
      throw signInError;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const verifySecondFactor = useCallback(
    async (method: 'totp' | 'recovery', code: string) => {
      if (!challengeToken) return;
      setIsSubmitting(true);
      setError(null);
      try {
        setStaff(await verifyStaffSecondFactor(challengeToken, method, code));
        setChallengeToken(null);
      } catch (verifyError) {
        setError(message(verifyError));
        throw verifyError;
      } finally {
        setIsSubmitting(false);
      }
    },
    [challengeToken],
  );

  const cancelSecondFactor = useCallback(() => {
    setChallengeToken(null);
    setError(null);
  }, []);

  const signOut = useCallback(async () => {
    setIsSubmitting(true);
    try {
      await signOutStaff();
      setStaff(null);
      setChallengeToken(null);
    } catch (signOutError) {
      setError(message(signOutError));
      throw signOutError;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      staff,
      challengeToken,
      isBootstrapping,
      isSubmitting,
      error,
      signIn,
      verifySecondFactor,
      cancelSecondFactor,
      signOut,
    }),
    [
      staff,
      challengeToken,
      isBootstrapping,
      isSubmitting,
      error,
      signIn,
      verifySecondFactor,
      cancelSecondFactor,
      signOut,
    ],
  );
  return <StaffAuthContext.Provider value={value}>{children}</StaffAuthContext.Provider>;
}

export function useStaffAuth() {
  const context = useContext(StaffAuthContext);
  if (!context) throw new Error('useStaffAuth must be used within StaffAuthProvider.');
  return context;
}
