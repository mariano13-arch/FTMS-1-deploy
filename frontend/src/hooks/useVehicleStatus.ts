import { useEffect, useState } from "react";
import {
  isNewerEvent,
  parseVehicleStatusMessage,
  vehicleStatusWebSocketUrl,
} from "../services/realtime";
import {
  getLatestStatus,
  type LatestStatusResponse,
} from "../services/telemetry";

export type RealtimeState =
  | "connecting"
  | "live"
  | "reconnecting"
  | "disconnected";

const maximumReconnectDelay = 30_000;

export function reconnectDelay(attempt: number): number {
  return Math.min(1_000 * 2 ** attempt, maximumReconnectDelay);
}

export function useVehicleStatus(deviceId: string) {
  const [status, setStatus] = useState<LatestStatusResponse | null>(null);
  const [requestState, setRequestState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [realtimeState, setRealtimeState] =
    useState<RealtimeState>("connecting");

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let pollId: number | null = null;
    let reconnectId: number | null = null;
    let reconnectAttempt = 0;
    const controllers = new Set<AbortController>();

    const applyStatus = (incoming: LatestStatusResponse) => {
      if (incoming.vehicle.device_id !== deviceId) return;
      setStatus((current) => {
        if (
          incoming.latest !== null &&
          isNewerEvent(incoming.latest, current?.latest ?? null)
        ) {
          return incoming;
        }
        if (current === null) return incoming;
        return current;
      });
      setRequestState("ready");
    };

    const fetchStatus = async () => {
      const controller = new AbortController();
      controllers.add(controller);
      try {
        const incoming = await getLatestStatus(deviceId, controller.signal);
        if (active) applyStatus(incoming);
      } catch (error: unknown) {
        if (
          active &&
          !(error instanceof DOMException && error.name === "AbortError")
        ) {
          setRequestState("error");
        }
      } finally {
        controllers.delete(controller);
      }
    };

    const stopPolling = () => {
      if (pollId !== null) {
        window.clearInterval(pollId);
        pollId = null;
      }
    };

    const stopFallback = () => {
      stopPolling();
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };

    const startFallback = () => {
      if (pollId !== null) return;
      void fetchStatus();
      pollId = window.setInterval(() => void fetchStatus(), 5_000);
    };

    const scheduleReconnect = () => {
      if (!active || reconnectId !== null) return;
      setRealtimeState("reconnecting");
      startFallback();
      const delay = reconnectDelay(reconnectAttempt);
      reconnectAttempt += 1;
      reconnectId = window.setTimeout(() => {
        reconnectId = null;
        connect();
      }, delay);
    };

    const connect = () => {
      if (!active || socket !== null) return;
      let candidate: WebSocket;
      try {
        candidate = new WebSocket(vehicleStatusWebSocketUrl(deviceId));
      } catch {
        setRealtimeState("disconnected");
        scheduleReconnect();
        return;
      }
      socket = candidate;
      candidate.onopen = () => {
        if (!active || socket !== candidate) return;
        setRealtimeState(reconnectAttempt === 0 ? "connecting" : "reconnecting");
      };
      candidate.onmessage = (event) => {
        if (!active || socket !== candidate) return;
        const message = parseVehicleStatusMessage(String(event.data), deviceId);
        if (!message) return;
        reconnectAttempt = 0;
        stopFallback();
        setRealtimeState("live");
        applyStatus(message.data);
      };
      candidate.onerror = () => {
        if (active && socket === candidate) candidate.close();
      };
      candidate.onclose = (event) => {
        if (!active || socket !== candidate) return;
        socket = null;
        if (event.code === 4404) {
          stopFallback();
          setRealtimeState("disconnected");
          return;
        }
        scheduleReconnect();
      };
    };

    void fetchStatus();
    connect();
    return () => {
      active = false;
      stopFallback();
      if (reconnectId !== null) window.clearTimeout(reconnectId);
      controllers.forEach((controller) => controller.abort());
      if (socket !== null) {
        const closingSocket = socket;
        socket = null;
        closingSocket.onopen = null;
        closingSocket.onmessage = null;
        closingSocket.onerror = null;
        closingSocket.onclose = null;
        closingSocket.close();
      }
    };
  }, [deviceId]);

  return { status, requestState, realtimeState };
}
