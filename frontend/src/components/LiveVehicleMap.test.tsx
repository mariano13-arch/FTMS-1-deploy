import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import LiveVehicleMap from "./LiveVehicleMap";
import type { TelemetryEvent } from "../services/telemetry";

const mocks = vi.hoisted(() => {
  const setView = vi.fn();
  return { setView, map: { setView } };
});
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TileLayer: ({ attribution }: { attribution: string }) => <span>{attribution}</span>,
  CircleMarker: ({ center }: { center: [number, number] }) => <span data-testid="marker">{center.join(",")}</span>,
  useMap: () => mocks.map,
}));
const latest: TelemetryEvent = {
  schema_version: "1.0", event_id: "event-1", sequence_number: 1,
  device_id: "LILYGO-001", recorded_at: "2026-07-30T00:00:00Z",
  received_at: "2026-07-30T00:00:01Z", latitude: 14.5, longitude: 121,
  gnss_speed_kph: 30, rpm: null, coolant_c: null, engine_load_pct: null,
  driving_event: "NORMAL",
};
beforeEach(() => mocks.setView.mockClear());

test("uses latitude-longitude order and recenters once for newer coordinates", () => {
  const { rerender } = render(<LiveVehicleMap latest={latest} />);
  expect(screen.getByTestId("marker")).toHaveTextContent("14.5,121");
  expect(mocks.setView).toHaveBeenLastCalledWith([14.5, 121]);
  rerender(<LiveVehicleMap latest={{ ...latest, event_id: "event-2", latitude: 15, longitude: 122 }} />);
  expect(mocks.setView).toHaveBeenCalledTimes(2);
  expect(mocks.setView).toHaveBeenLastCalledWith([15, 122]);
});

test("a clock-only parent rerender does not recenter unchanged coordinates", () => {
  const { rerender } = render(<LiveVehicleMap latest={latest} />);
  rerender(<LiveVehicleMap latest={{ ...latest }} />);
  expect(mocks.setView).toHaveBeenCalledTimes(1);
});
