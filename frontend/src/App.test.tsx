import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

const health = { status: "ok", service: "ftms-backend", database: "ok" };
const waiting = {
  vehicle: {
    device_id: "LILYGO-001",
    plate_number: "DEMO-001",
    display_name: "Sprint 1 Demo Vehicle",
  },
  latest: null,
};
const latest = {
  ...waiting,
  latest: {
    schema_version: "1.0",
    event_id: "evt-1",
    sequence_number: 1,
    device_id: "LILYGO-001",
    recorded_at: "2026-07-29T01:18:20Z",
    received_at: "2026-07-29T01:18:21Z",
    latitude: 14.5186,
    longitude: 121.0196,
    gnss_speed_kph: 38.2,
    rpm: null,
    coolant_c: 88,
    engine_load_pct: 34,
    driving_event: "NORMAL",
  },
};

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("preserves health state and shows the waiting state", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(Response.json(health))
    .mockResolvedValueOnce(Response.json(waiting));

  render(<App />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText(/Backend connection: Connected/)).toBeInTheDocument();
  expect(await screen.findByText(/Waiting for the first telemetry event/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Simulated Pilot Data" })).toBeInTheDocument();
});

test("renders the latest telemetry and unavailable nullable values", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(Response.json(health))
    .mockResolvedValueOnce(Response.json(latest));

  render(<App />);

  expect(await screen.findByText("38.2 km/h")).toBeInTheDocument();
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
  expect(screen.getByText("88 °C")).toBeInTheDocument();
  expect(screen.getByText("14.5186, 121.0196")).toBeInTheDocument();
  expect(screen.getByText("Sprint 1 Demo Vehicle")).toBeInTheDocument();
  expect(screen.getByText("Recorded at")).toBeInTheDocument();
  expect(screen.getByText("Received at")).toBeInTheDocument();
  expect(screen.getByText(new Date(latest.latest.recorded_at).toLocaleString())).toBeInTheDocument();
  expect(screen.getByText(new Date(latest.latest.received_at).toLocaleString())).toBeInTheDocument();
});

test("shows an independent latest-status error", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(Response.json(health))
    .mockResolvedValueOnce(new Response(null, { status: 503 }));

  render(<App />);

  expect(await screen.findByText("Latest-status request failed.")).toBeInTheDocument();
  expect(screen.getByText(/Backend connection: Connected/)).toBeInTheDocument();
});

test("shows backend unavailable when the health request fails", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(null, { status: 503 }),
  );

  render(<App />);

  expect(await screen.findByText("Backend unavailable.")).toBeInTheDocument();
  expect(screen.getByText(/Backend connection: Error/)).toBeInTheDocument();
});

test("polls latest status every five seconds and cleans up", async () => {
  vi.useFakeTimers();
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(Response.json(health))
    .mockResolvedValue(Response.json(waiting));

  const { unmount } = render(<App />);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(fetchMock).toHaveBeenCalledTimes(2);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(fetchMock).toHaveBeenCalledTimes(3);

  unmount();
  await vi.advanceTimersByTimeAsync(5_000);
  expect(fetchMock).toHaveBeenCalledTimes(3);
});
