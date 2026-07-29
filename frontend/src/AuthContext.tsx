import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "./services/api";
import * as auth from "./services/auth";
import type { StaffUser } from "./services/auth";

type AuthState = {
  user: StaffUser | null; loading: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>; expire: () => void;
};
const Context = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<StaffUser | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);
  const actionControllers = useRef(new Set<AbortController>());
  const signInInFlight = useRef(false);
  const signOutInFlight = useRef(false);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const controllers = actionControllers.current;
    let active = true;
    const expire = () => { if (active) setUser(null); };
    window.addEventListener("ftms:session-expired", expire);
    auth.bootstrapCsrf(controller.signal)
      .then(() => auth.me(controller.signal))
      .then((restored) => { if (active) setUser(restored); })
      .catch((error: unknown) => {
        if (
          active &&
          !(error instanceof DOMException && error.name === "AbortError") &&
          !(error instanceof ApiError && error.status === 401)
        ) setUser(null);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => {
      active = false; mounted.current = false; controller.abort();
      controllers.forEach((item) => item.abort());
      controllers.clear();
      window.removeEventListener("ftms:session-expired", expire);
    };
  }, []);
  const value = useMemo<AuthState>(() => ({
    user, loading,
    signIn: async (username, password) => {
      if (signInInFlight.current) return;
      signInInFlight.current = true;
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        const signedIn = await auth.login(username, password, controller.signal);
        if (mounted.current) setUser(signedIn);
      } finally {
        actionControllers.current.delete(controller);
        signInInFlight.current = false;
      }
    },
    signOut: async () => {
      if (signOutInFlight.current) return;
      signOutInFlight.current = true;
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        await auth.logout(controller.signal);
        if (mounted.current) setUser(null);
      } finally {
        actionControllers.current.delete(controller);
        signOutInFlight.current = false;
      }
    },
    expire: () => { if (mounted.current) setUser(null); },
  }), [user, loading]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("AuthProvider is required");
  return value;
}
