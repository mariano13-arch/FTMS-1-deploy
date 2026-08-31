import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import App from "../../App";

const featureLabelForTest = (value: string) => value
  .replaceAll("_", " ")
  .replace("km per h", "km/h")
  .replace(" pct", " (%)")
  .replace(/\b\w/g, letter => letter.toUpperCase());

const mocks = vi.hoisted(() => ({
  getDashboard: vi.fn(),
  getModelInfo: vi.fn(),
  getReadiness: vi.fn(),
}));

vi.mock("./api", async importOriginal => ({
  ...await importOriginal<typeof import("./api")>(),
  getFuelDashboard: mocks.getDashboard,
  getFuelModelInfo: mocks.getModelInfo,
  getFuelReadiness: mocks.getReadiness,
}));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "manager", display_name: "Fleet Manager", role: "FLEET_MANAGER" },
    loading: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
    expire: vi.fn(),
  }),
}));

const modelInfo = {
  model_name: "FTMS XGBoost Fuel Consumption Estimator",
  model_version: "experiment-3-tuned",
  model_type: "XGBoost Regressor",
  model_role: "Selected simpler deployable candidate",
  target: "estimated_fuel_lph",
  features: ["Vehicle_Speed_km_per_h", "Engine_RPM_RPM", "Absolute_Load_pct", "OAT_DegC", "Short_Term_Fuel_Trim_Bank_1_pct", "Short_Term_Fuel_Trim_Bank_2_pct", "Long_Term_Fuel_Trim_Bank_1_pct", "Long_Term_Fuel_Trim_Bank_2_pct", "Generalized_Weight"],
  excluded_leakage_features: ["MAF_g_per_sec", "log_MAF"],
  metrics: { mae_lph: 1.0523, rmse_lph: 1.6703, r2: 0.7333 },
  hyperparameters: { n_estimators: 350 },
  prediction_semantics: "Model estimate only; not actual or measured fuel consumption.",
  accuracy_note: "Experiment 1 has better predictive accuracy; Experiment 3 Tuned was selected as the simpler deployable candidate.",
  availability: "available",
  is_estimate: true,
} as const;

const readiness = {
  inputs: modelInfo.features.map((feature, index) => ({
    feature,
    status: index < 2 ? "available" : index === 2 ? "unverified" : "missing",
    source: index === 0 ? "TelemetryEvent.gnss_speed_kph" : index === 1 ? "TelemetryEvent.rpm" : null,
    note: "No matching persisted operational source is currently available.",
  })),
  latest_telemetry: null,
  latest_operational_result: {
    status: "prediction_blocked",
    model_name: modelInfo.model_name,
    model_version: modelInfo.model_version,
    target: "estimated_fuel_lph",
    estimated_fuel_lph: null,
    input_timestamp: null,
    inputs: {},
    missing_features: modelInfo.features.slice(2),
    invalid_features: [],
    unexpected_features: [],
    is_estimate: true,
  },
} as const;

const blockedVehicle = {
  vehicle_id: 1,
  vehicle_name: "Fuel Analytics Van",
  plate_number: "ABC-123",
  device_id: "FUEL-001",
  telemetry_status: "available",
  telemetry_timestamp: "2026-08-26T01:00:00Z",
  latest_estimated_fuel_lph: null,
  prediction_status: "prediction_blocked",
  last_prediction_at: null,
  prediction_source_mode: null,
  prediction_source_label: null,
  latest_prediction_input_timestamp: null,
  latest_prediction_inputs: [],
  is_demo_prediction: false,
  input_readiness: {
    available_count: 2,
    required_count: 9,
    available_features: modelInfo.features.slice(0, 2),
    missing_features: modelInfo.features.slice(3),
    unverified_features: ["Absolute_Load_pct"],
  },
} as const;

const emptyDashboard = {
  refreshed_at: "2026-08-26T02:00:00Z",
  model_availability: "available",
  demo_data_present: false,
  demo_data_note: null,
  filters: { range: "24h", vehicle_id: null, selected_vehicle: null, trend_aggregation: "hourly average" },
  summary: { vehicle_count: 1, prediction_ready_count: 0, demo_ready_count: 0, prediction_blocked_count: 1, average_estimated_fuel_lph: null, demo_average_estimated_fuel_lph: null },
  trend: [],
  vehicle_comparison: [],
  readiness_breakdown: { ready: 0, demo_ready: 0, blocked: 1, no_telemetry: 0, model_unavailable: 0 },
  vehicle_options: [{ vehicle_id: 1, vehicle_name: "Fuel Analytics Van", plate_number: "ABC-123", device_id: "FUEL-001" }],
  vehicle_pagination: { page: 1, page_size: 10, total_count: 18, total_pages: 2, start: 1, end: 10 },
  vehicles: [blockedVehicle],
} as const;

const populatedDashboard = {
  ...emptyDashboard,
  summary: { vehicle_count: 1, prediction_ready_count: 1, demo_ready_count: 0, prediction_blocked_count: 0, average_estimated_fuel_lph: 3.82, demo_average_estimated_fuel_lph: null },
  trend: [
    { timestamp: "2026-08-26T00:00:00Z", estimated_fuel_lph: 3.4 },
    { timestamp: "2026-08-26T01:00:00Z", estimated_fuel_lph: 3.82 },
  ],
  vehicle_comparison: [{ vehicle_id: 1, vehicle_name: "Fuel Analytics Van", plate_number: "ABC-123", estimated_fuel_lph: 3.82, predicted_at: "2026-08-26T01:00:00Z", source_mode: "explicit_validated_api", source_label: "Validated API Inputs", is_demo_prediction: false }],
  readiness_breakdown: { ready: 1, demo_ready: 0, blocked: 0, no_telemetry: 0, model_unavailable: 0 },
  vehicles: [{ ...blockedVehicle, latest_estimated_fuel_lph: 3.82, prediction_status: "prediction_available", last_prediction_at: "2026-08-26T01:00:00Z" }],
} as const;

const demoInputs = modelInfo.features.map((feature, index) => ({
  feature,
  value: index === 0 ? 48.25 : index === 1 ? 2100 : index === 8 ? 1500 : 30,
  unit: index === 0 ? "km/h" : index === 1 ? "RPM" : index === 3 ? "°C" : index === 8 ? null : "%",
  source: index < 2 ? "Actual persisted telemetry" : "Demo/Test Input",
}));

const demoDashboard = {
  ...emptyDashboard,
  demo_data_present: true,
  demo_data_note: "Demo prediction records are used for system verification and are not operational fuel measurements.",
  summary: { vehicle_count: 1, prediction_ready_count: 0, demo_ready_count: 1, prediction_blocked_count: 0, average_estimated_fuel_lph: null, demo_average_estimated_fuel_lph: 3.25 },
  trend: [{ timestamp: "2026-08-26T01:00:00Z", estimated_fuel_lph: 3.25 }],
  vehicle_comparison: [{ vehicle_id: 1, vehicle_name: "Sprint 1 Demo Vehicle", plate_number: "DEMO-001", estimated_fuel_lph: 3.25, predicted_at: "2026-08-26T01:00:00Z", source_mode: "demo_seed", source_label: "Demo/Test Inputs", is_demo_prediction: true }],
  readiness_breakdown: { ready: 0, demo_ready: 1, blocked: 0, no_telemetry: 0, model_unavailable: 0 },
  vehicle_options: [{ vehicle_id: 1, vehicle_name: "Sprint 1 Demo Vehicle", plate_number: "DEMO-001", device_id: "DEMO-001" }],
  vehicles: [{
    ...blockedVehicle,
    vehicle_name: "Sprint 1 Demo Vehicle",
    plate_number: "DEMO-001",
    device_id: "DEMO-001",
    latest_estimated_fuel_lph: 3.25,
    prediction_status: "demo_ready",
    last_prediction_at: "2026-08-26T01:00:00Z",
    prediction_source_mode: "demo_seed",
    prediction_source_label: "Demo/Test Inputs",
    latest_prediction_input_timestamp: "2026-08-26T01:00:00Z",
    latest_prediction_inputs: demoInputs,
    is_demo_prediction: true,
    input_readiness: { available_count: 9, required_count: 9, available_features: modelInfo.features, missing_features: [], unverified_features: [] },
  }],
} as const;

const renderRoute = () => render(<MemoryRouter initialEntries={["/fuel-analytics"]}><App /></MemoryRouter>);

beforeEach(() => {
  mocks.getDashboard.mockReset().mockResolvedValue(emptyDashboard);
  mocks.getModelInfo.mockReset().mockResolvedValue(modelInfo);
  mocks.getReadiness.mockReset().mockResolvedValue(readiness);
});

test("renders the operational dashboard, four KPIs, honest empty charts, and blocked row", async () => {
  renderRoute();

  expect(await screen.findByRole("heading", { name: "Fleet Fuel Analytics" })).toBeInTheDocument();
  for (const label of ["Fleet Vehicles", "Prediction Ready", "Average Estimated Fuel Rate", "Prediction Blocked"]) expect(screen.getByText(label)).toBeInTheDocument();
  expect(screen.getByText("No prediction history yet")).toBeInTheDocument();
  expect(screen.getByText("No vehicle estimates available")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Prediction readiness for 1 fleet vehicle/ })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Overview/ })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("tab", { name: /Fleet Status/ }));
  expect(screen.getByRole("heading", { name: "Fleet Fuel Status" })).toBeInTheDocument();
  expect(screen.getByText("Showing 10 of 1 vehicles")).toBeInTheDocument();
  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.queryByText(/0\.00 L\/h/)).not.toBeInTheDocument();
});

test("renders real trend and comparison data with explicit model-estimate units", async () => {
  mocks.getDashboard.mockResolvedValue(populatedDashboard);
  const view = renderRoute();

  expect(await screen.findByRole("img", { name: /2 persisted prediction points/ })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /fuel rate comparison by vehicle/i })).toBeInTheDocument();
  expect(screen.getByText("Current estimate")).toBeInTheDocument();
  expect(screen.getByText("Average estimate")).toBeInTheDocument();
  expect(screen.getByText("Observed prediction range")).toBeInTheDocument();
  expect(screen.getByText(/Actual measured fuel and a validated prediction interval are not available/)).toBeInTheDocument();
  const trendPoints = view.container.querySelectorAll(".fuel-trend-point");
  expect(trendPoints).toHaveLength(2);
  fireEvent.mouseEnter(trendPoints[0]);
  expect(screen.getByText("3.40 L/h estimate")).toBeInTheDocument();
  expect(screen.getAllByText("3.82 L/h").length).toBeGreaterThanOrEqual(2);
  expect(screen.getAllByText(/Model estimate/i).length).toBeGreaterThan(0);
});

test("renders demo estimates with honest source labels and all nine model inputs", async () => {
  mocks.getDashboard.mockResolvedValue(demoDashboard);
  renderRoute();

  expect(await screen.findByText("DEMO ANALYTICS DATA")).toBeInTheDocument();
  expect(screen.getByText("Demo/Test Dataset")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /1 persisted prediction point/ })).toBeInTheDocument();
  expect(screen.getAllByText(/Demo\/Test/).length).toBeGreaterThan(0);
  expect(screen.getByText(/not operational fuel measurements/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: /Fleet Status/ }));
  expect(screen.getByText("Demo Ready")).toBeInTheDocument();
  expect(screen.getAllByText(/Source: Demo\/Test Inputs/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "View" }));
  expect(screen.getByRole("dialog", { name: /Sprint 1 Demo Vehicle fuel detail/ })).toBeInTheDocument();
  expect(screen.getAllByText("Actual persisted telemetry")).toHaveLength(2);
  expect(screen.getAllByText("Demo/Test Input")).toHaveLength(7);
  for (const feature of modelInfo.features) expect(screen.getByText(featureLabelForTest(feature))).toBeInTheDocument();
  expect(screen.getByText(/not an operational fuel measurement/)).toBeInTheDocument();
});

test("vehicle detail explains blocked missing and unverified inputs", async () => {
  renderRoute();
  fireEvent.click(await screen.findByRole("tab", { name: /Fleet Status/ }));
  fireEvent.click(await screen.findByRole("button", { name: "View" }));

  expect(screen.getByRole("dialog", { name: /Fuel Analytics Van fuel detail/ })).toBeInTheDocument();
  expect(screen.getByText("Prediction status").nextSibling).toHaveTextContent("Blocked");
  expect(screen.getAllByText("Absolute Load (%)").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Generalized Weight").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "Close vehicle fuel detail" }));
  expect(screen.queryByRole("dialog", { name: /Fuel Analytics Van fuel detail/ })).not.toBeInTheDocument();
});

test("vehicle and time controls request filtered backend history", async () => {
  renderRoute();
  await screen.findByRole("heading", { name: "Fleet Fuel Analytics" });
  fireEvent.change(screen.getByLabelText("Trend vehicle"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "7 Days" }));

  await waitFor(() => expect(mocks.getDashboard).toHaveBeenCalledWith("7d", 1, "", expect.any(AbortSignal)));
});

test("searches fleet rows with suggestions and restores all rows when cleared", async () => {
  renderRoute();
  fireEvent.click(await screen.findByRole("tab", { name: /Fleet Status/ }));
  await screen.findByRole("heading", { name: "Fleet Fuel Status" });

  expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
  const search = screen.getByRole("combobox", { name: "Search vehicles" });
  fireEvent.change(search, { target: { value: "Fuel" } });
  expect(screen.getByRole("option", { name: /Fuel Analytics Van/ })).toBeInTheDocument();
  await waitFor(() => expect(mocks.getDashboard).toHaveBeenLastCalledWith("24h", null, "Fuel", expect.any(AbortSignal)));

  fireEvent.change(search, { target: { value: "" } });
  await waitFor(() => expect(mocks.getDashboard).toHaveBeenLastCalledWith("24h", null, "", expect.any(AbortSignal)));
});

test("keeps operational input readiness while technical model details live in settings", async () => {
  renderRoute();

  fireEvent.click(await screen.findByRole("tab", { name: /Input Readiness/ }));
  expect(screen.getByRole("heading", { name: "Model Input Readiness" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: /Model Details/ })).not.toBeInTheDocument();
});

test("shows loading, backend error, and model-unavailable states distinctly", async () => {
  mocks.getDashboard.mockReturnValueOnce(new Promise(() => undefined));
  const loading = renderRoute();
  expect(screen.getByRole("status")).toHaveTextContent("Loading Fleet Fuel Analytics");
  loading.unmount();

  mocks.getDashboard.mockRejectedValueOnce(new Error("backend unavailable"));
  const failed = renderRoute();
  expect(await screen.findByRole("alert")).toHaveTextContent("backend unavailable");
  failed.unmount();

  mocks.getDashboard.mockResolvedValueOnce({ ...emptyDashboard, model_availability: "unavailable", readiness_breakdown: { ready: 0, demo_ready: 0, blocked: 0, no_telemetry: 0, model_unavailable: 1 } });
  renderRoute();
  expect(await screen.findByRole("alert")).toHaveTextContent("selected model is unavailable");
  expect(screen.getAllByText(/Model unavailable/i).length).toBeGreaterThan(0);
});
