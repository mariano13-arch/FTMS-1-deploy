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
  bootstrapDriverCsrf,
  getCurrentDriver,
  signInDriver,
  signOutDriver,
} from '@/services/driverAuth';
import type { DriverIdentity } from '@/types';

type DriverAuthContextValue = {
  driver: DriverIdentity | null;
  isBootstrapping: boolean;
  isSubmitting: boolean;
  error: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const DriverAuthContext = createContext<DriverAuthContextValue | null>(null);

function errorMessage(error: unknown, invalidCredentialsMessage: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return invalidCredentialsMessage;
    }
    return error.message;
  }
  return 'An unexpected authentication error occurred.';
}

export function DriverAuthProvider({ children }: PropsWithChildren) {
  const [driver, setDriver] = useState<DriverIdentity | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function bootstrapSession() {
      try {
        await bootstrapDriverCsrf(controller.signal);
        setDriver(await getCurrentDriver(controller.signal));
      } catch (bootstrapError) {
        if (bootstrapError instanceof Error && bootstrapError.name === 'AbortError') {
          return;
        }
        setDriver(null);
        if (!(bootstrapError instanceof ApiError && bootstrapError.status === 401)) {
          setError(errorMessage(bootstrapError, 'Driver session is unavailable.'));
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsBootstrapping(false);
        }
      }
    }

    void bootstrapSession();
    return () => controller.abort();
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    setIsSubmitting(true);
    setError(null);
    try {
      setDriver(await signInDriver(username, password));
    } catch (signInError) {
      setDriver(null);
      setError(errorMessage(signInError, 'Unable to sign in with those credentials.'));
      throw signInError;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      await signOutDriver();
      setDriver(null);
    } catch (signOutError) {
      setError(errorMessage(signOutError, 'Unable to sign out. Please try again.'));
      throw signOutError;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const value = useMemo(
    () => ({ driver, isBootstrapping, isSubmitting, error, signIn, signOut }),
    [driver, error, isBootstrapping, isSubmitting, signIn, signOut],
  );

  return <DriverAuthContext.Provider value={value}>{children}</DriverAuthContext.Provider>;
}

export function useDriverAuth() {
  const context = useContext(DriverAuthContext);
  if (!context) {
    throw new Error('useDriverAuth must be used within DriverAuthProvider.');
  }
  return context;
}
