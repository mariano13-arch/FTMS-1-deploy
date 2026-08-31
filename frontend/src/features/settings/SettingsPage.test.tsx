import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryHistory } from "history";
import { MemoryRouter, Router } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import AiModelsSettingsPage from "./AiModelsSettingsPage";
import SettingsPage from "./SettingsPage";
import { IntegrationsSettingsPage, OperationalRulesSettingsPage, SecuritySettingsPage } from "./SettingsStaticPages";

const mocks = vi.hoisted(() => ({ fuelModel: vi.fn(), fuelReadiness: vi.fn(), maintenanceModel: vi.fn(), maintenanceReadiness: vi.fn() }));
vi.mock("../fuel-analytics/api", () => ({ getFuelModelInfo: mocks.fuelModel, getFuelReadiness: mocks.fuelReadiness }));
vi.mock("../maintenance/api", () => ({ getMaintenanceModelInfo: mocks.maintenanceModel, getMaintenanceReadiness: mocks.maintenanceReadiness }));

const fuelModel = { model_name: "FTMS Fuel Estimator", model_version: "experiment-3", model_type: "XGBoost Regressor", model_role: "Selected deployable candidate", target: "estimated_fuel_lph", features: ["engine_load", "rpm"], excluded_leakage_features: [], metrics: { mae_lph: 1, rmse_lph: 2, r2: .8 }, hyperparameters: {}, prediction_semantics: "model_estimate", accuracy_note: "Estimated fuel rate is not measured consumption.", availability: "available", is_estimate: true };
const fuelReadiness = { inputs: [{ feature: "engine_load", status: "available", source: "telemetry", note: "" }, { feature: "rpm", status: "missing", source: null, note: "not mapped" }], latest_telemetry: null, latest_operational_result: {} };
const maintenanceModel = { model_name: "engine_fault_xgboost_obd_candidate_v2", model_version: "2.0", contract_version: "2.0", features: ["MAP", "TPS", "RPM", "Speed"], decision_threshold: .52, deployment_state: "research_candidate", production_ready: false, score_semantics: "uncalibrated_model_score" };
const maintenanceReadiness = { deployment_state: "research_candidate", production_ready: false, direct_obd_feed_allowed: false, unit_scaling_verified: false, vehicle_compatibility_verified: false, blocking_reason: "Scaling and vehicle compatibility must be verified.", required_features: maintenanceModel.features, source_modes: [] };

beforeEach(() => {
  mocks.fuelModel.mockReset().mockResolvedValue(fuelModel);
  mocks.fuelReadiness.mockReset().mockResolvedValue(fuelReadiness);
  mocks.maintenanceModel.mockReset().mockResolvedValue(maintenanceModel);
  mocks.maintenanceReadiness.mockReset().mockResolvedValue(maintenanceReadiness);
});

const renderAt = (element: ReactNode, path: string) => render(<MemoryRouter initialEntries={[path]}>{element}</MemoryRouter>);

describe("System Rules & Settings workspace", () => {
  test("renders the compact Overview with truthful category statuses", () => {
    renderAt(<SettingsPage />, "/settings");
    expect(screen.getByRole("link", { name: "Overview" })).toHaveClass("active");
    expect(screen.getByRole("heading", { name: "Settings Overview" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /AI \/ ML Models/ }).find((link) => link.textContent?.includes("Available"))).toBeDefined();
    expect(screen.getAllByRole("link", { name: /Integrations/ }).find((link) => link.textContent?.includes("Status unavailable"))).toBeDefined();
    expect(screen.queryByText(/Staff Users|Roles & Permissions|Audit Logs/)).not.toBeInTheDocument();
  });

  test("uses route navigation and active state without localStorage", () => {
    const history = createMemoryHistory({ initialEntries: ["/settings"] });
    const storage = vi.spyOn(Storage.prototype, "setItem");
    render(<Router history={history}><SettingsPage /></Router>);
    fireEvent.click(screen.getByRole("link", { name: "Security" }));
    expect(history.location.pathname).toBe("/settings/security");
    expect(screen.getByRole("link", { name: "Security" })).toHaveClass("active");
    history.goBack();
    expect(history.location.pathname).toBe("/settings");
    expect(storage).not.toHaveBeenCalled();
    storage.mockRestore();
  });

  test("shows planned Security capabilities without fake controls", () => {
    renderAt(<SecuritySettingsPage />, "/settings/security");
    expect(screen.getByRole("link", { name: "Security" })).toHaveClass("active");
    for (const section of ["Two-Factor Authentication", "Password", "Active Sessions"]) expect(screen.getByText(section)).toBeInTheDocument();
    expect(screen.getAllByText("Planned")).toHaveLength(3);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("shows only truthful read-only Operational Rules", () => {
    renderAt(<OperationalRulesSettingsPage />, "/settings/operational-rules");
    expect(screen.getByRole("link", { name: "Operational Rules" })).toHaveClass("active");
    expect(screen.getByText(/Human dispatch confirmation remains mandatory/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/OR-Tools parameter|automatic dispatch enabled/i)).not.toBeInTheDocument();
  });

  test("does not claim integrations are configured or expose secrets", () => {
    renderAt(<IntegrationsSettingsPage />, "/settings/integrations");
    expect(screen.getByRole("link", { name: "Integrations" })).toHaveClass("active");
    expect(screen.getAllByText("Not configured")).toHaveLength(2);
    expect(screen.getAllByText("Status unavailable")).toHaveLength(3);
    expect(screen.queryByText(/^Configured$/)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/api[_ -]?key|smtp password|bearer token|secret:/i);
  });

  test("renders real Fuel and Maintenance technical information only on AI Models", async () => {
    renderAt(<AiModelsSettingsPage />, "/settings/ai-models");
    expect(screen.getByText("Loading AI / ML model status…")).toBeInTheDocument();
    expect(await screen.findByText("Fuel Analytics Model")).toBeInTheDocument();
    expect(screen.getByText("FTMS Fuel Estimator · experiment-3")).toBeInTheDocument();
    expect(screen.getByText("XGBoost Regressor")).toBeInTheDocument();
    expect(screen.getByText("1 / 2 available")).toBeInTheDocument();
    expect(screen.getByText("Maintenance Prediction Model")).toBeInTheDocument();
    expect(screen.getByText("research_candidate")).toBeInTheDocument();
    expect(screen.getByText("0.52")).toBeInTheDocument();
    expect(screen.getByText("uncalibrated_model_score")).toBeInTheDocument();
    for (const feature of ["MAP", "TPS", "RPM", "Speed"]) expect(screen.getByText(feature)).toBeInTheDocument();
    expect(screen.getByText(/Mechanic confirmation required/)).toBeInTheDocument();
    expect(screen.queryByText(/Fleet Fuel Status|vehicle inspection|Add User/)).not.toBeInTheDocument();
  });

  test("shows a controlled AI model API error", async () => {
    mocks.fuelModel.mockRejectedValue(new Error("offline"));
    renderAt(<AiModelsSettingsPage />, "/settings/ai-models");
    expect(await screen.findByRole("alert")).toHaveTextContent("Model status unavailable");
  });
});
