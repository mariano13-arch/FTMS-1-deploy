import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { MemoryRouter, Router } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "../../services/api";
import StaffSetupPasswordPage from "./StaffSetupPasswordPage";

const mocks = vi.hoisted(() => ({ setupStaffPassword: vi.fn() }));
vi.mock("./api", () => ({ setupStaffPassword: mocks.setupStaffPassword }));

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><StaffSetupPasswordPage /></MemoryRouter>);
}
function fill(password = "A-secure-staff-password-42!", confirmation = password) {
  fireEvent.change(screen.getByLabelText("New Password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm Password"), { target: { value: confirmation } });
}

beforeEach(() => mocks.setupStaffPassword.mockReset());
afterEach(() => vi.restoreAllMocks());

describe("public staff password setup", () => {
  test("reads uid/token from the query and submits matching passwords without browser storage", async () => {
    const localSpy = vi.spyOn(Storage.prototype, "setItem");
    mocks.setupStaffPassword.mockResolvedValue(undefined);
    const history = createMemoryHistory({ initialEntries: ["/setup-staff-password?uid=safe-uid&token=safe-token"] });
    render(<Router history={history}><StaffSetupPasswordPage /></Router>);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("heading", { name: "Password set successfully" })).toBeInTheDocument();
    expect(mocks.setupStaffPassword).toHaveBeenCalledWith({ uid: "safe-uid", token: "safe-token", new_password: "A-secure-staff-password-42!", confirm_password: "A-secure-staff-password-42!" }, expect.any(AbortSignal));
    expect(localSpy).not.toHaveBeenCalled();
    expect(history.location.search).toBe("");
    expect(screen.getByRole("link", { name: "Go to Staff Login" })).toHaveAttribute("href", "/login");
  });

  test("treats a real HTTP 204 as success under StrictMode without parsing its empty body", async () => {
    const actual = await vi.importActual<typeof import("./api")>("./api");
    mocks.setupStaffPassword.mockImplementation(actual.setupStaffPassword);
    const emptyBodyJson = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "test-csrf" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce({ status: 204, ok: true, json: emptyBodyJson } as unknown as Response);
    const history = createMemoryHistory({ initialEntries: ["/setup-staff-password?uid=safe-uid&token=safe-token"] });
    render(<StrictMode><Router history={history}><StaffSetupPasswordPage /></Router></StrictMode>);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("heading", { name: "Password set successfully" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Setting password…" })).not.toBeInTheDocument();
    expect(history.location.search).toBe("");
    expect(emptyBodyJson).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("blocks password mismatch before sending a request", () => {
    renderAt("/setup-staff-password?uid=safe-uid&token=safe-token");
    fill("A-secure-staff-password-42!", "different");
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(mocks.setupStaffPassword).not.toHaveBeenCalled();
  });

  test("renders backend password validation errors", async () => {
    mocks.setupStaffPassword.mockImplementation(async () => { throw new ApiError(400, { new_password: ["This password is too common."] }); });
    renderAt("/setup-staff-password?uid=safe-uid&token=safe-token");
    fill("password");
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This password is too common.");
  });

  test("shows the controlled invalid/expired/inactive setup-link state", async () => {
    mocks.setupStaffPassword.mockImplementation(async () => { throw new ApiError(400, { detail: "Invalid or expired setup link." }); });
    renderAt("/setup-staff-password?uid=safe-uid&token=safe-token");
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Set Password" }));
    expect(await screen.findByRole("heading", { name: "Setup link unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/invalid, expired, inactive/)).toBeInTheDocument();
  });

  test("shows loading while setup is pending and prevents duplicate submission", async () => {
    let resolve!: () => void;
    mocks.setupStaffPassword.mockImplementation(() => new Promise<void>((done) => { resolve = done; }));
    renderAt("/setup-staff-password?uid=safe-uid&token=safe-token");
    fill();
    const form = screen.getByRole("button", { name: "Set Password" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(await screen.findByRole("button", { name: "Setting password…" })).toBeDisabled();
    expect(mocks.setupStaffPassword).toHaveBeenCalledTimes(1);
    await act(async () => resolve());
    await waitFor(() => expect(screen.getByRole("heading", { name: "Password set successfully" })).toBeInTheDocument());
  });
});
