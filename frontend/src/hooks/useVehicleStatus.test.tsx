import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { useVehicleStatus } from "./useVehicleStatus";
import type { LatestStatusResponse, TelemetryEvent } from "../services/telemetry";

const getLatestStatus = vi.hoisted(() => vi.fn());
vi.mock("../services/telemetry", async (original) => ({
  ...(await original()), getLatestStatus,
}));

const baseEvent: TelemetryEvent = {
  schema_version: "1.0", event_id: "event-1", sequence_number: 1,
  device_id: "LILYGO-001", recorded_at: "2026-07-30T00:00:00Z",
  received_at: "2026-07-30T00:00:01Z", latitude: 14.5, longitude: 121,
  gnss_speed_kph: 30, rpm: null, coolant_c: null, engine_load_pct: null,
  driving_event: "NORMAL",
};
const status: LatestStatusResponse = {
  vehicle: { device_id: "LILYGO-001", plate_number: "DEMO-001", display_name: "Pilot" },
  latest: baseEvent,
};
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeWebSocket.instances.push(this); }
  open() { this.onopen?.(); }
  message(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent); }
  raw(value: string) { this.onmessage?.({ data: value } as MessageEvent); }
  close(code = 1006) {
    if (this.closed) return; this.closed = true;
    this.onclose?.({ code } as CloseEvent);
  }
}
const message = (latest: TelemetryEvent = baseEvent) => ({
  type: "vehicle.status.updated",
  data: { ...status, latest },
});

beforeEach(() => {
  FakeWebSocket.instances = [];
  getLatestStatus.mockReset().mockResolvedValue(status);
  vi.stubGlobal("WebSocket", FakeWebSocket);
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
});

describe("useVehicleStatus lifecycle", () => {
  test("loads latest REST status immediately after mounting", async () => {
    const { result } = renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    expect(getLatestStatus).toHaveBeenCalledWith("LILYGO-001", expect.any(AbortSignal));
    expect(result.current.status?.latest?.event_id).toBe("event-1");
  });

  test("applies a snapshot/update but cannot regress to an older event", async () => {
    const { result } = renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    const socket = FakeWebSocket.instances[0];
    const newer = { ...baseEvent, event_id: "newer", sequence_number: 2, recorded_at: "2026-07-30T00:01:00Z", latitude: 15 };
    act(() => { socket.open(); socket.message(message(newer)); });
    expect(result.current.status?.latest?.event_id).toBe("newer");
    act(() => socket.message(message(baseEvent)));
    expect(result.current.status?.latest?.event_id).toBe("newer");
  });

  test("ignores malformed and wrong-device messages", async () => {
    const { result } = renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    const socket = FakeWebSocket.instances[0];
    act(() => {
      socket.raw("{");
      socket.message({
        ...message(), data: {
          ...status,
          vehicle: { ...status.vehicle, device_id: "OTHER" },
          latest: { ...baseEvent, device_id: "OTHER" },
        },
      });
    });
    expect(result.current.status?.vehicle.device_id).toBe("LILYGO-001");
  });

  test("rapid open-close cycles use exponential delays capped at 30 seconds", async () => {
    vi.useFakeTimers(); renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    for (const [index, delay] of [1000, 2000, 4000, 8000, 16000, 30000].entries()) {
      act(() => { FakeWebSocket.instances[index].open(); FakeWebSocket.instances[index].close(); });
      await act(async () => vi.advanceTimersByTimeAsync(delay - 1));
      expect(FakeWebSocket.instances).toHaveLength(index + 1);
      await act(async () => vi.advanceTimersByTimeAsync(1));
      expect(FakeWebSocket.instances).toHaveLength(index + 2);
    }
  });

  test("a valid message resets reconnect backoff", async () => {
    vi.useFakeTimers(); renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    act(() => FakeWebSocket.instances[0].close());
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    act(() => {
      FakeWebSocket.instances[1].message(message());
      FakeWebSocket.instances[1].close();
    });
    await act(async () => vi.advanceTimersByTimeAsync(999));
    expect(FakeWebSocket.instances).toHaveLength(2);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  test.each([4401, 4403, 4404])(
    "permanent close %s creates no socket, timer, or fallback polling",
    async (code) => {
      vi.useFakeTimers(); renderHook(() => useVehicleStatus("LILYGO-001"));
      await act(async () => Promise.resolve());
      const calls = getLatestStatus.mock.calls.length;
      act(() => FakeWebSocket.instances[0].close(code));
      await act(async () => vi.advanceTimersByTimeAsync(60_000));
      expect(FakeWebSocket.instances).toHaveLength(1);
      expect(getLatestStatus).toHaveBeenCalledTimes(calls);
    },
  );

  test("temporary close starts immediate fallback and valid message stops it", async () => {
    vi.useFakeTimers(); renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    const initial = getLatestStatus.mock.calls.length;
    act(() => FakeWebSocket.instances[0].close());
    await act(async () => Promise.resolve());
    expect(getLatestStatus).toHaveBeenCalledTimes(initial + 1);
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    act(() => FakeWebSocket.instances[1].message(message()));
    await act(async () => vi.advanceTimersByTimeAsync(10_000));
    expect(getLatestStatus).toHaveBeenCalledTimes(initial + 1);
  });

  test("obsolete socket handlers cannot affect the current connection", async () => {
    vi.useFakeTimers(); const { result } = renderHook(() => useVehicleStatus("LILYGO-001"));
    await act(async () => Promise.resolve());
    const obsolete = FakeWebSocket.instances[0];
    act(() => obsolete.close());
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    const current = FakeWebSocket.instances[1];
    act(() => current.message(message({ ...baseEvent, event_id: "current", sequence_number: 2 })));
    act(() => obsolete.message(message({ ...baseEvent, event_id: "obsolete", sequence_number: 99 })));
    expect(result.current.status?.latest?.event_id).toBe("current");
  });

  test("unmount aborts requests and closes the socket without reconnecting", async () => {
    vi.useFakeTimers();
    let observedSignal: AbortSignal | undefined;
    getLatestStatus.mockImplementation((_id, signal) => {
      observedSignal = signal; return new Promise(() => undefined);
    });
    const { unmount } = renderHook(() => useVehicleStatus("LILYGO-001"));
    const socket = FakeWebSocket.instances[0];
    unmount();
    expect(observedSignal?.aborted).toBe(true);
    expect(socket.closed).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
