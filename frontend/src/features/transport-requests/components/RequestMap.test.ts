import { describe, expect, test } from "vitest";
import {
  activeRouteLinePaint,
  fleetVehicleMarker,
  plannedRouteLinePaint,
  routeCasingPaint,
  trafficLayerId,
  tripRouteLayerOrder,
} from "./RequestMap";

describe("active-trip route styling", () => {
  test("uses the same strong solid style and casing for both trip legs", () => {
    expect(plannedRouteLinePaint).toEqual(activeRouteLinePaint);
    expect(activeRouteLinePaint).toMatchObject({
      "line-color": "#263d73",
      "line-width": 6,
      "line-opacity": 0.96,
    });
    expect(plannedRouteLinePaint).not.toHaveProperty("line-dasharray");
    expect(activeRouteLinePaint).not.toHaveProperty("line-dasharray");
    expect(routeCasingPaint).toMatchObject({
      "line-width": 10,
      "line-opacity": 0.72,
    });
  });

  test("keeps every trip route layer in the top stack above traffic", () => {
    expect(tripRouteLayerOrder).toEqual([
      "request-planned-route-casing",
      "request-planned-route-line",
      "request-route-casing",
      "request-route-line",
    ]);
    expect(tripRouteLayerOrder).not.toContain(trafficLayerId);
  });
});

describe("emergency fleet marker", () => {
  test("keeps the vehicle marker clickable and adds emergency emphasis only when active", () => {
    const active = fleetVehicleMarker("SOS Vehicle", "live", "GNSS", {
      activatedAt: "2026-09-24T01:02:03Z",
    });
    const normal = fleetVehicleMarker("Normal Vehicle", "live", "GNSS", null);
    expect(active.tagName).toBe("BUTTON");
    expect(active).toHaveClass("request-map-marker--emergency");
    expect(active).toHaveAttribute("data-emergency", "SOS");
    expect(normal).not.toHaveClass("request-map-marker--emergency");
  });
});
