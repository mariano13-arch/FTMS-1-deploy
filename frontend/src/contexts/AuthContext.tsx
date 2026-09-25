import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../services/api";
import * as auth from "../services/auth";
import type { LoginResult, StaffUser } from "../services/auth";

type AuthState = {
  user: StaffUser | null; loading: boolean; sessionMessage: string;
  signIn: (username: string, password: string) => Promise<LoginResult>;
  completeTwoFactor: (challengeToken: string, method: "totp" | "recovery", code: string) => Promise<void>;
  completeRequiredMfaEnrollment: (challengeToken: string, code: string) => Promise<string[]>;
  activateEnrolledSession: () => Promise<void>;
  signOut: () => Promise<void>; expire: () => void;
};
const Context = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<StaffUser | null>(null);
  const [sessionMessage, setSessionMessage] = useState("");
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
    const expire = (event: Event) => {
      if (!active) return;
      const detail = (event as CustomEvent<{ message?: string }>).detail;
      setSessionMessage(detail?.message ?? "Your session expired. Please sign in again.");
      setUser(null);
      auth.clearClientAuthentication();
    };
    window.addEventListener("ftms:session-expired", expire);
    const passwordChanged = () => { if (active) { setUser(null); setSessionMessage(""); } };
    window.addEventListener("ftms:password-changed", passwordChanged);
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
      window.removeEventListener("ftms:password-changed", passwordChanged);
    };
  }, []);
  useEffect(() => {
    if (!user) return undefined;
    const idleTimeoutMs = Number(import.meta.env.VITE_SESSION_IDLE_TIMEOUT_SECONDS ?? "43200") * 1000;
    const reportIntervalMs = 60_000;
    let lastInteraction = Date.now();
    let lastReport = Date.now();
    let activityPending = false;
    let expired = false;
    const channel = typeof BroadcastChannel === "undefined"
      ? null
      : new BroadcastChannel("ftms-session-activity");
    const reportPendingActivity = (now: number) => {
      if (!activityPending || now - lastReport < reportIntervalMs) return;
      activityPending = false;
      lastReport = now;
      void auth.reportActivity().catch(() => undefined);
    };
    const markActivity = () => {
      lastInteraction = Date.now();
      activityPending = true;
      channel?.postMessage("activity");
      reportPendingActivity(lastInteraction);
    };
    const receiveActivity = () => { lastInteraction = Date.now(); };
    channel?.addEventListener("message", receiveActivity);
    const eventNames: (keyof WindowEventMap)[] = [
      "keydown", "click", "pointerdown", "touchstart", "scroll",
    ];
    eventNames.forEach((name) => window.addEventListener(name, markActivity, { passive: true }));
    const timer = window.setInterval(() => {
      const now = Date.now();
      if (!expired && now - lastInteraction >= idleTimeoutMs) {
        expired = true;
        void auth.logout().catch(() => undefined).finally(() => {
          if (mounted.current) {
            auth.clearClientAuthentication();
            setSessionMessage("Your session expired due to inactivity. Please sign in again.");
            setUser(null);
          }
        });
        return;
      }
      reportPendingActivity(now);
    }, 1_000);
    return () => {
      window.clearInterval(timer);
      eventNames.forEach((name) => window.removeEventListener(name, markActivity));
      channel?.removeEventListener("message", receiveActivity);
      channel?.close();
    };
  }, [user]);
  const value = useMemo<AuthState>(() => ({
    user, loading, sessionMessage,
    signIn: async (username, password) => {
      if (signInInFlight.current) throw new Error("Sign-in is already in progress.");
      signInInFlight.current = true;
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        if (mounted.current) setSessionMessage("");
        const signedIn = await auth.login(username, password, controller.signal);
        if (signedIn.kind === "authenticated" && mounted.current) setUser(signedIn.user);
        return signedIn;
      } finally {
        actionControllers.current.delete(controller);
        signInInFlight.current = false;
      }
    },
    completeTwoFactor: async (challengeToken, method, code) => {
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        if (mounted.current) setSessionMessage("");
        const signedIn = await auth.verifyTwoFactor(challengeToken, method, code, controller.signal);
        if (mounted.current) setUser(signedIn);
      } finally { actionControllers.current.delete(controller); }
    },
    completeRequiredMfaEnrollment: async (challengeToken, code) => {
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        if (mounted.current) setSessionMessage("");
        const result = await auth.confirmRequiredMfaEnrollment(
          challengeToken, code, controller.signal,
        );
        return result.recoveryCodes;
      } finally { actionControllers.current.delete(controller); }
    },
    activateEnrolledSession: async () => {
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        const enrolledUser = await auth.me(controller.signal);
        if (mounted.current) setUser(enrolledUser);
      } finally { actionControllers.current.delete(controller); }
    },
    signOut: async () => {
      if (signOutInFlight.current) return;
      signOutInFlight.current = true;
      const controller = new AbortController(); actionControllers.current.add(controller);
      try {
        await auth.logout(controller.signal);
        if (mounted.current) { setUser(null); setSessionMessage(""); }
      } finally {
        actionControllers.current.delete(controller);
        signOutInFlight.current = false;
      }
    },
    expire: () => { if (mounted.current) setUser(null); },
  }), [user, loading, sessionMessage]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("AuthProvider is required");
  return value;
}
