import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import { api } from "../services/api";

const user = { id: 1, username: "manager", display_name: "Fleet Manager", role: "FLEET_MANAGER" as const };
function json(value: unknown, status = 200) {
  return Promise.resolve(Response.json(value, { status }));
}
function Consumer() {
  const auth = useAuth();
  return <div>
    <span>{auth.loading ? "loading" : auth.user?.username ?? "anonymous"}</span>
    <span>{auth.sessionMessage}</span>
    <button onClick={() => void auth.signIn("manager", "supplied-password").catch(() => undefined)}>login</button>
    <button onClick={() => void auth.signOut().catch(() => undefined)}>logout</button>
  </div>;
}
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

function authenticatedFetch(input: RequestInfo | URL) {
  const url = String(input);
  if (url.includes("/auth/csrf/")) return json({ csrf_token: "token" });
  if (url.includes("/auth/me/")) return json({ user });
  if (url.includes("/auth/activity/")) return Promise.resolve(new Response(null, { status: 204 }));
  if (url.includes("/auth/logout/")) return Promise.resolve(new Response(null, { status: 204 }));
  return json({});
}

test("CSRF bootstrap precedes session restoration and includes credentials", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockImplementationOnce(() => json({ csrf_token: "bootstrap-token" }))
    .mockImplementationOnce(() => json({ user }));
  render(<AuthProvider><Consumer /></AuthProvider>);
  expect(await screen.findByText("manager")).toBeInTheDocument();
  expect(String(fetchMock.mock.calls[0][0])).toContain("/auth/csrf/");
  expect(String(fetchMock.mock.calls[1][0])).toContain("/auth/me/");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ credentials: "include" });
});

test("login sends bootstrap CSRF and stores the rotated token", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockImplementationOnce(() => json({ csrf_token: "initial-token" }))
    .mockImplementationOnce(() => json(null, 401))
    .mockImplementationOnce(() => json({ csrf_token: "login-token" }))
    .mockImplementationOnce(() => json({ user, csrf_token: "rotated-token" }))
    .mockImplementationOnce(() => Promise.resolve(new Response(null, { status: 204 })));
  render(<AuthProvider><Consumer /></AuthProvider>);
  await screen.findByText("anonymous");
  fireEvent.click(screen.getByText("login"));
  await screen.findByText("manager");
  const loginHeaders = fetchMock.mock.calls[3][1]?.headers as Headers;
  expect(loginHeaders.get("X-CSRFToken")).toBe("login-token");
  expect(fetchMock.mock.calls[3][1]).toMatchObject({ credentials: "include" });
  fireEvent.click(screen.getByText("logout"));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
  const logoutHeaders = fetchMock.mock.calls[4][1]?.headers as Headers;
  expect(logoutHeaders.get("X-CSRFToken")).toBe("rotated-token");
});

test("a REST 401 expires the restored frontend session", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockImplementationOnce(() => json({ csrf_token: "token" }))
    .mockImplementationOnce(() => json({ user }))
    .mockImplementationOnce(() => json({ detail: "expired" }, 401));
  render(<AuthProvider><Consumer /></AuthProvider>);
  await screen.findByText("manager");
  await act(async () => { await api("/api/v1/protected/").catch(() => undefined); });
  expect(screen.getByText("anonymous")).toBeInTheDocument();
});

test("15 minutes without interaction logs out and displays the inactivity message", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(authenticatedFetch);
  render(<AuthProvider><Consumer /></AuthProvider>);
  await act(async () => undefined);
  expect(screen.getByText("manager")).toBeInTheDocument();

  await act(async () => { await vi.advanceTimersByTimeAsync(899_000); });
  expect(screen.getByText("manager")).toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });

  expect(screen.getByText("anonymous")).toBeInTheDocument();
  expect(screen.getByText("Your session expired due to inactivity. Please sign in again.")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/auth/logout/"))).toBe(true);
});

test("meaningful interaction resets idle time and is reported at most once per minute", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(authenticatedFetch);
  render(<StrictMode><AuthProvider><Consumer /></AuthProvider></StrictMode>);
  await act(async () => undefined);

  await act(async () => { await vi.advanceTimersByTimeAsync(840_000); });
  fireEvent.scroll(window);
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  fireEvent.keyDown(window, { key: "Tab" });
  fireEvent.click(window);
  await act(async () => { await vi.advanceTimersByTimeAsync(59_000); });

  expect(screen.getByText("manager")).toBeInTheDocument();
  let activityCalls = fetchMock.mock.calls.filter(([input]) =>
    String(input).includes("/auth/activity/"));
  expect(activityCalls).toHaveLength(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
  activityCalls = fetchMock.mock.calls.filter(([input]) =>
    String(input).includes("/auth/activity/"));
  expect(activityCalls).toHaveLength(3);
});

test("background API traffic does not reset the local idle countdown", async () => {
  vi.useFakeTimers();
  vi.spyOn(globalThis, "fetch").mockImplementation(authenticatedFetch);
  render(<AuthProvider><Consumer /></AuthProvider>);
  await act(async () => undefined);

  await act(async () => { await vi.advanceTimersByTimeAsync(840_000); });
  await act(async () => { await api("/api/v1/background-poll/"); });
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

  expect(screen.getByText("anonymous")).toBeInTheDocument();
});

test("unmount aborts unresolved bootstrap without post-unmount updates", () => {
  let signal: AbortSignal | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
    signal = init?.signal ?? undefined;
    return new Promise(() => undefined);
  });
  const { unmount } = render(<AuthProvider><Consumer /></AuthProvider>);
  unmount();
  expect(signal?.aborted).toBe(true);
});

test("StrictMode replay still handles login and aborts it on real unmount", async () => {
  let loginSignal: AbortSignal | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/auth/csrf/")) return json({ csrf_token: "token" });
    if (url.includes("/auth/me/")) return json(null, 401);
    loginSignal = init?.signal ?? undefined;
    return new Promise(() => undefined);
  });
  const rendered = render(<StrictMode><AuthProvider><Consumer /></AuthProvider></StrictMode>);
  await screen.findByText("anonymous");
  fireEvent.click(screen.getByText("login"));
  await waitFor(() => expect(loginSignal).toBeDefined());
  rendered.unmount();
  expect(loginSignal?.aborted).toBe(true);
});

test("StrictMode replay still handles logout and aborts it on real unmount", async () => {
  let logoutSignal: AbortSignal | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/auth/csrf/")) return json({ csrf_token: "token" });
    if (url.includes("/auth/me/")) return json({ user });
    logoutSignal = init?.signal ?? undefined;
    return new Promise(() => undefined);
  });
  const rendered = render(<StrictMode><AuthProvider><Consumer /></AuthProvider></StrictMode>);
  await screen.findByText("manager");
  fireEvent.click(screen.getByText("logout"));
  await waitFor(() => expect(logoutSignal).toBeDefined());
  rendered.unmount();
  expect(logoutSignal?.aborted).toBe(true);
});
