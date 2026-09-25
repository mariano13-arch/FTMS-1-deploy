import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { MemoryRouter, Router } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import ForgotPasswordPage from "./ForgotPasswordPage";
import LoginPage from "./LoginPage";
import ResetPasswordPage from "./ResetPasswordPage";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: null, sessionMessage: "", signIn: vi.fn(), completeTwoFactor: vi.fn() }),
}));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

beforeEach(() => vi.restoreAllMocks());

describe("staff password recovery", () => {
  test("login links to forgot password", () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/forgot-password");
  });

  test("request form submits and always shows the generic success state", async () => {
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json({ csrf_token: "csrf" }))
      .mockResolvedValueOnce(json({ detail: "If an eligible account matches that email, a password reset link has been sent." }));
    render(<MemoryRouter><ForgotPasswordPage /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "staff@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent("If an eligible account matches that email");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  test("reset validates confirmation and handles invalid links", async () => {
    const history = createMemoryHistory({ initialEntries: ["/reset-password?uid=abc&token=token"] });
    render(<Router history={history}><ResetPasswordPage /></Router>);
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "one" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "two" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Passwords do not match");
  });

  test("reset success clears token parameters and offers sign in", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json({ csrf_token: "csrf" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const history = createMemoryHistory({ initialEntries: ["/reset-password?uid=abc&token=token"] });
    render(<Router history={history}><ResetPasswordPage /></Router>);
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "A-strong-password-42!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "A-strong-password-42!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Password changed");
    await waitFor(() => expect(history.location.search).toBe(""));
  });

  test("reset shows the server's invalid-token state", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json({ csrf_token: "csrf" }))
      .mockResolvedValueOnce(json({ detail: "Invalid or expired password reset link." }, 400));
    render(<MemoryRouter initialEntries={["/reset-password?uid=abc&token=bad"]}><ResetPasswordPage /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "A-strong-password-42!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "A-strong-password-42!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired password reset link");
  });
});
