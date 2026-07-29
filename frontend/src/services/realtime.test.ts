import { describe, expect, test } from "vitest";
import { parseVehicleStatusMessage } from "./realtime";

const event = {
  schema_version: "1.0", event_id: "event-1", sequence_number: 1,
  device_id: "LILYGO-001", recorded_at: "2026-07-30T00:00:00Z",
  received_at: "2026-07-30T00:00:01Z", latitude: 14.5, longitude: 121,
  gnss_speed_kph: 30, rpm: null, coolant_c: null, engine_load_pct: null,
  driving_event: "NORMAL",
};
const payload = (overrides = {}) => JSON.stringify({
  type: "vehicle.status.updated",
  data: {
    vehicle: { device_id: "LILYGO-001", plate_number: "DEMO-001", display_name: "Pilot" },
    latest: { ...event, ...overrides },
  },
});

describe("vehicle status message validation", () => {
  test("accepts nullable OBD-II values", () => {
    expect(parseVehicleStatusMessage(payload(), "LILYGO-001")?.data.latest?.rpm).toBeNull();
  });
  test.each([
    ["recorded_at", "not-a-date"], ["received_at", ""],
    ["latitude", 91], ["longitude", 181], ["latitude", Number.NaN],
    ["sequence_number", -1], ["sequence_number", Number.MAX_SAFE_INTEGER + 1],
    ["gnss_speed_kph", 301], ["rpm", 12001], ["engine_load_pct", 101],
  ])("rejects invalid %s", (field, value) => {
    expect(parseVehicleStatusMessage(payload({ [field]: value }), "LILYGO-001")).toBeNull();
  });
  test("rejects a wrong inner device ID", () => {
    expect(parseVehicleStatusMessage(payload({ device_id: "OTHER" }), "LILYGO-001")).toBeNull();
  });
});
