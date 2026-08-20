import { StrictMode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { MemoryRouter, Route, Router } from "react-router-dom";
import { afterEach, describe, expect, test, vi } from "vitest";
import { apiBaseUrl } from "../../services/api";
import SetupPasswordPage from "./SetupPasswordPage";

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(
    status === 204 ? null : JSON.stringify(body),
    { status, headers: { "Content-Type": "application/json" } },
  ));
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => { resolve = yes; });
  return { promise, resolve };
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Route path="/setup-password"><SetupPasswordPage /></Route></MemoryRouter>);
}

function renderStrictAt(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  return {
    history,
    ...render(<StrictMode><Router history={history}><SetupPasswordPage /></Router></StrictMode>),
  };
}

function fillPasswords(password = "A-private-driver-password-42!", confirmation = password) {
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: confirmation } });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("public driver password setup", () => {
  test("missing setup credentials show a controlled invalid-link state without a request", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderAt("/setup-password");
    expect(screen.getByRole("heading", { name: "Setup link unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/incomplete or invalid/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("valid query credentials show the password form without staff navigation", () => {
    renderAt("/setup-password?uid=dummy-uid&token=dummy-token");
    expect(screen.getByRole("heading", { name: "Set up your Driver account" })).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  test("mismatched passwords are blocked before any API request", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords("A-private-driver-password-42!", "A-different-password-42!");
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("submits CSRF and password requests, then removes credentials from the URL", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => response(null, 204));
    const history = createMemoryHistory({ initialEntries: ["/setup-password?uid=dummy-uid&token=dummy-token"] });
    render(<Router history={history}><SetupPasswordPage /></Router>);
    fillPasswords();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));

    expect(await screen.findByRole("heading", { name: "Password set successfully" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${apiBaseUrl}/api/v1/driver-auth/csrf/`);
    expect(String(fetchMock.mock.calls[1][0])).toBe(`${apiBaseUrl}/api/v1/driver-auth/setup-password/`);
    const request = fetchMock.mock.calls[1][1]!;
    expect(request.method).toBe("POST");
    expect(request.credentials).toBe("include");
    expect((request.headers as Headers).get("X-CSRFToken")).toBe("test-csrf");
    expect(JSON.parse(String(request.body))).toEqual({
      uid: "dummy-uid",
      token: "dummy-token",
      new_password: "A-private-driver-password-42!",
      confirm_password: "A-private-driver-password-42!",
    });
    expect(history.location.pathname).toBe("/setup-password");
    expect(history.location.search).toBe("");
  });

  test("prevents duplicate submission while the setup request is pending", async () => {
    const pending = deferred<Response>();
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => pending.promise);
    renderAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords();
    const form = screen.getByRole("button", { name: "Set Password" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(await screen.findByRole("button", { name: "Setting password…" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => pending.resolve(await response(null, 204)));
    expect(await screen.findByRole("heading", { name: "Password set successfully" })).toBeInTheDocument();
  });

  test("shows all safe backend password validation messages", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => response({ new_password: ["This password is too short.", "This password is too common."] }, 400));
    renderAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords("password");
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This password is too short.");
    expect(alert).toHaveTextContent("This password is too common.");
    expect(screen.getByRole("button", { name: "Set Password" })).toBeEnabled();
    expect(screen.getByLabelText("New password")).toHaveValue("password");
  });

  test("recovers from a detail error under StrictMode", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => response({ detail: "The submitted password could not be accepted." }, 400));
    const { history } = renderStrictAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The submitted password could not be accepted.");
    expect(screen.getByRole("button", { name: "Set Password" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Setting password…" })).not.toBeInTheDocument();
    expect(history.location.search).toBe("?uid=dummy-uid&token=dummy-token");
  });

  test("shows non-field validation errors and re-enables submission", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => response({ non_field_errors: ["The password could not be accepted."] }, 400));
    renderAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The password could not be accepted.");
    expect(screen.getByRole("button", { name: "Set Password" })).toBeEnabled();
  });

  test("shows safe validation arrays from other DRF fields", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => response({ uid: ["This field is invalid."], token: ["This field is required."] }, 400));
    renderAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This field is invalid.");
    expect(alert).toHaveTextContent("This field is required.");
    expect(screen.getByRole("button", { name: "Set Password" })).toBeEnabled();
  });

  test("recovers from a network failure with a safe message", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("Network unavailable"));
    renderStrictAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to set your password. Please try again.");
    expect(screen.getByRole("button", { name: "Set Password" })).toBeEnabled();
  });

  test("shows a controlled state for an invalid, expired, or used token", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => response({ csrf_token: "test-csrf" }))
      .mockImplementationOnce(() => response({ detail: "Invalid or expired setup link." }, 400));
    renderStrictAt("/setup-password?uid=dummy-uid&token=dummy-token");
    fillPasswords();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("heading", { name: "Setup link unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/invalid, expired, or has already been used/)).toBeInTheDocument();
  });
});
