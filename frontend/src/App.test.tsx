import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { reconnectDelay } from "./hooks/useVehicleStatus";
import type {
  LatestStatusResponse,
  TelemetryEvent,
} from "./services/telemetry";

const { setViewMock, mapMock } = vi.hoisted(() => {
  const setView = vi.fn();
  return { setViewMock: setView, mapMock: { setView } };
});

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="map">{children}</div>
  ),
  TileLayer: ({ attribution }: { attribution: string }) => (
    <span>{attribution.replace("&copy;", "©")}</span>
  ),
  CircleMarker: ({ center }: { center: [number, number] }) => (
    <span data-testid="marker">{center.join(",")}</span>
  ),
  useMap: () => mapMock,
}));

const health = { status: "ok", service: "ftms-backend", database: "ok" };
const waiting: LatestStatusResponse = {
  vehicle: {
    device_id: "LILYGO-001",
    plate_number: "DEMO-001",
    display_name: "Sprint 1 Demo Vehicle",
  },
  latest: null,
};
const latestEvent: TelemetryEvent = {
  schema_version: "1.0",
  event_id: "evt-1",
  sequence_number: 1,
  device_id: "LILYGO-001",
  recorded_at: new Date(Date.now() - 10_000).toISOString(),
  received_at: new Date(Date.now() - 9_000).toISOString(),
  latitude: 14.5186,
  longitude: 121.0196,
  gnss_speed_kph: 38.2,
  rpm: null,
  coolant_c: 88,
  engine_load_pct: 34,
  driving_event: "NORMAL",
};
const latest: LatestStatusResponse = {
  ...waiting,
  latest: latestEvent,
};

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.onopen?.();
  }

  message(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent);
  }

  malformed() {
    this.onmessage?.({ data: "{" } as MessageEvent);
  }

  close(code = 1006) {
    if (this.closed) return;
    this.closed = true;
    this.onclose?.({ code } as CloseEvent);
  }
}

function mockFetch(status: LatestStatusResponse = waiting) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    return Promise.resolve(
      Response.json(url.includes("/health/") ? health : status),
    );
  });
}

function update(overrides: Partial<TelemetryEvent> = {}) {
  return {
    type: "vehicle.status.updated",
    data: { ...latest, latest: { ...latestEvent, ...overrides } },
  };
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  setViewMock.mockClear();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Sprint 2 vehicle status", () => {
  test("loads REST identity and preserves loading, waiting, and pilot states", async () => {
    mockFetch();
    render(<App />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText(/Backend connection: Connected/)).toBeInTheDocument();
    expect(screen.getByText(/Waiting for the first telemetry event/)).toBeInTheDocument();
    expect(screen.getByText(/Waiting for live vehicle location/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Simulated Pilot Data" })).toBeInTheDocument();
  });

  test("renders REST telemetry, timestamps, nullable values, and map order", async () => {
    mockFetch(latest);
    render(<App />);

    expect(await screen.findByText("38.2 km/h")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText(new Date(latestEvent.recorded_at).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText(new Date(latestEvent.received_at).toLocaleString())).toBeInTheDocument();
    expect(screen.getByTestId("marker")).toHaveTextContent("14.5186,121.0196");
    expect(screen.getByText("© OpenStreetMap contributors")).toBeInTheDocument();
    expect(screen.getByText(/Current position: 14.5186, 121.0196/)).toBeInTheDocument();
  });

  test("WebSocket snapshot and update display immediately and move the marker", async () => {
    mockFetch();
    render(<App />);
    await screen.findByText(/Waiting for the first telemetry event/);
    const socket = FakeWebSocket.instances[0];

    act(() => {
      socket.open();
      socket.message({ type: "vehicle.status.snapshot", data: latest });
    });
    expect(screen.getByText(/Real-time status: Live/)).toBeInTheDocument();
    expect(screen.getByTestId("marker")).toHaveTextContent("14.5186,121.0196");

    act(() => socket.message(update({
      event_id: "evt-2",
      sequence_number: 2,
      recorded_at: new Date(Date.now()).toISOString(),
      latitude: 14.52,
      longitude: 121.02,
    })));
    expect(screen.getByTestId("marker")).toHaveTextContent("14.52,121.02");
  });

  test("ignores older, malformed, and other-device messages", async () => {
    mockFetch(latest);
    render(<App />);
    await screen.findByTestId("marker");
    const socket = FakeWebSocket.instances[0];

    act(() => {
      socket.malformed();
      socket.message(update({
        event_id: "older",
        sequence_number: 0,
        recorded_at: new Date(Date.now() - 60_000).toISOString(),
        latitude: 1,
        longitude: 2,
      }));
      socket.message({
        ...update({ latitude: 3, longitude: 4 }),
        data: {
          ...latest,
          vehicle: { ...latest.vehicle, device_id: "OTHER" },
          latest: { ...latestEvent, device_id: "OTHER" },
        },
      });
    });

    expect(screen.getByTestId("marker")).toHaveTextContent("14.5186,121.0196");
  });

  test("disconnect starts immediate five-second fallback and reconnect stops it", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch(latest);
    render(<App />);
    await act(async () => Promise.resolve());
    const baseline = fetchMock.mock.calls.length;

    act(() => FakeWebSocket.instances[0].close());
    expect(screen.getByText(/Reconnecting \/ REST fallback/)).toBeInTheDocument();
    await act(async () => Promise.resolve());
    expect(fetchMock.mock.calls.length).toBe(baseline + 1);

    await act(async () => vi.advanceTimersByTimeAsync(5_000));
    expect(fetchMock.mock.calls.length).toBe(baseline + 2);
    act(() => {
      const reconnected = FakeWebSocket.instances.at(-1);
      reconnected?.open();
      reconnected?.message({ type: "vehicle.status.snapshot", data: latest });
    });
    await act(async () => vi.advanceTimersByTimeAsync(5_000));
    expect(fetchMock.mock.calls.length).toBe(baseline + 2);
  });

  test("rapid open-close cycles increase actual reconnect delays to the cap", async () => {
    vi.useFakeTimers();
    mockFetch();
    render(<App />);
    await act(async () => Promise.resolve());

    for (const [index, delay] of [1_000, 2_000, 4_000, 8_000, 16_000, 30_000].entries()) {
      const socket = FakeWebSocket.instances[index];
      act(() => {
        socket.open();
        socket.close();
      });
      await act(async () => vi.advanceTimersByTimeAsync(delay - 1));
      expect(FakeWebSocket.instances).toHaveLength(index + 1);
      await act(async () => vi.advanceTimersByTimeAsync(1));
      expect(FakeWebSocket.instances).toHaveLength(index + 2);
    }

    const cappedSocket = FakeWebSocket.instances.at(-1)!;
    act(() => {
      cappedSocket.open();
      cappedSocket.close();
    });
    await act(async () => vi.advanceTimersByTimeAsync(29_999));
    expect(FakeWebSocket.instances).toHaveLength(7);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(FakeWebSocket.instances).toHaveLength(8);
    expect(reconnectDelay(20)).toBe(30_000);
  });

  test("a valid message resets backoff and permanent 4404 does not retry", async () => {
    vi.useFakeTimers();
    mockFetch();
    render(<App />);
    await act(async () => Promise.resolve());
    act(() => FakeWebSocket.instances[0].close());
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    act(() => {
      FakeWebSocket.instances[1].open();
      FakeWebSocket.instances[1].message({
        type: "vehicle.status.snapshot",
        data: waiting,
      });
      FakeWebSocket.instances[1].close(4404);
    });
    expect(screen.getByText(/Real-time status: Disconnected/)).toBeInTheDocument();
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  test("obsolete socket handlers cannot affect a newer socket", async () => {
    vi.useFakeTimers();
    mockFetch();
    render(<App />);
    await act(async () => Promise.resolve());
    const obsolete = FakeWebSocket.instances[0];
    const obsoleteClose = obsolete.onclose;
    act(() => obsolete.close());
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    const current = FakeWebSocket.instances[1];

    act(() => obsoleteClose?.({ code: 1006 } as CloseEvent));
    await act(async () => vi.advanceTimersByTimeAsync(2_000));

    expect(current.closed).toBe(false);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  test("unmount closes sockets, aborts requests, and clears timers", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch(latest);
    const { unmount } = render(<App />);
    await act(async () => Promise.resolve());
    act(() => FakeWebSocket.instances[0].close());
    const callsBeforeUnmount = fetchMock.mock.calls.length;

    unmount();
    expect(FakeWebSocket.instances.every((socket) => socket.closed)).toBe(true);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchMock.mock.calls.length).toBe(callsBeforeUnmount);
  });

  test("unmount aborts an active latest-status request", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).includes("/health/")) return Promise.resolve(Response.json(health));
      return new Promise<Response>(() => undefined);
    });
    const { unmount } = render(<App />);
    await act(async () => Promise.resolve());
    const statusCall = vi.mocked(fetch).mock.calls.find(
      ([input]) => String(input).includes("/latest-status/"),
    );
    const signal = statusCall?.[1]?.signal;

    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  test("renders stale and error states independently", async () => {
    const stale = {
      ...latest,
      latest: {
        ...latestEvent,
        recorded_at: new Date(Date.now() - 61_000).toISOString(),
      },
    };
    mockFetch(stale);
    render(<App />);
    expect(await screen.findByText("Stale telemetry")).toBeInTheDocument();
  });

  test("shows reconnecting fallback when WebSocket construction fails", async () => {
    mockFetch();
    vi.stubGlobal("WebSocket", class {
      constructor() {
        throw new Error("unavailable");
      }
    });
    render(<App />);
    expect(
      await screen.findByText(/Real-time status: Reconnecting \/ REST fallback/),
    ).toBeInTheDocument();
  });

  test("rejects mismatched inner devices, invalid dates, coordinates, and numbers", async () => {
    mockFetch(latest);
    render(<App />);
    await screen.findByTestId("marker");
    const socket = FakeWebSocket.instances[0];
    const invalidMessages = [
      update({ device_id: "OTHER", latitude: 1 }),
      update({ recorded_at: "not-a-date", latitude: 2 }),
      update({ received_at: "not-a-date", latitude: 3 }),
      update({ latitude: 91 }),
      update({ longitude: 181 }),
      update({ sequence_number: -1, latitude: 4 }),
      update({ sequence_number: Number.MAX_SAFE_INTEGER + 1, latitude: 4 }),
      update({ gnss_speed_kph: Number.POSITIVE_INFINITY, latitude: 5 }),
      update({ gnss_speed_kph: 301, latitude: 5 }),
      update({ rpm: 12_001, latitude: 6 }),
      update({ engine_load_pct: 101, latitude: 7 }),
    ];

    act(() => invalidMessages.forEach((message) => socket.message(message)));

    expect(screen.getByTestId("marker")).toHaveTextContent("14.5186,121.0196");
  });

  test("accepts valid nullable OBD-II values", async () => {
    mockFetch();
    render(<App />);
    await screen.findByText(/Waiting for the first telemetry event/);
    act(() => FakeWebSocket.instances[0].message(update({
      rpm: null,
      coolant_c: null,
      engine_load_pct: null,
    })));
    expect(screen.getAllByText("Unavailable")).toHaveLength(3);
  });

  test("freshness clock does not recenter until newer coordinates arrive", async () => {
    vi.useFakeTimers();
    mockFetch(latest);
    render(<App />);
    await act(async () => Promise.resolve());
    expect(setViewMock).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    expect(setViewMock).toHaveBeenCalledTimes(1);

    act(() => FakeWebSocket.instances[0].message(update({
      event_id: "moved",
      sequence_number: 2,
      recorded_at: new Date(Date.now()).toISOString(),
      latitude: 14.52,
      longitude: 121.02,
    })));
    expect(setViewMock).toHaveBeenCalledTimes(2);
    expect(setViewMock).toHaveBeenLastCalledWith([14.52, 121.02]);

    act(() => FakeWebSocket.instances[0].message(update({
      event_id: "older-position",
      sequence_number: 0,
      recorded_at: new Date(Date.now() - 60_000).toISOString(),
      latitude: 1,
      longitude: 2,
    })));
    expect(setViewMock).toHaveBeenCalledTimes(2);
  });

  test("shows the latest-status error while backend health remains connected", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(
      String(input).includes("/health/")
        ? Response.json(health)
        : new Response(null, { status: 503 }),
    ));
    render(<App />);
    expect(await screen.findByText("Latest-status request failed.")).toBeInTheDocument();
    expect(screen.getByText(/Backend connection: Connected/)).toBeInTheDocument();
  });
});
