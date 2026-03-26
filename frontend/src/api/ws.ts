/** WebSocket client — auto-reconnect, dispatches to Zustand stores.
 *
 * Per frontend/CLAUDE.md: Components never touch WS directly.
 * This module manages the connection and routes typed messages to stores.
 */

import type { WSMessage } from "../types";
import type { BridgeStatus } from "../types/bridge";
import { useBridgeStore } from "../stores/bridgeStore";
import { useConsoleStore } from "../stores/consoleStore";
import { useIngestionStore } from "../stores/ingestionStore";
import { useStrataLiveStore } from "../stores/strataLiveStore";
import { mapWSMessageToEntries, resetMapperState } from "../utils/consoleMapper";
import { queryClient } from "./queryClient";

const WS_PORT = import.meta.env.VITE_WS_PORT ?? "8000";
const WS_URL = `ws://${window.location.hostname}:${WS_PORT}/ws`;

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let backoff = 1000; // ms, doubles on each failure up to 30s
const MAX_BACKOFF = 30000;

/** Previous bridge status for detecting transitions to "running". */
let prevBridgeStatus: BridgeStatus | null = null;

function dispatchToConsole(msg: WSMessage): void {
  const entries = mapWSMessageToEntries(msg);
  const { addEntry } = useConsoleStore.getState();
  for (const entry of entries) {
    addEntry(entry);
  }
}

function dispatch(msg: WSMessage): void {
  switch (msg.type) {
    case "bridge_status": {
      const newStatus = msg.payload.status;

      // Invalidate network queries when bridge transitions to "running"
      // from any non-running state (including null initial state).
      if (newStatus === "running" && prevBridgeStatus !== "running") {
        queryClient.invalidateQueries({ queryKey: ["network", "route"] });
        queryClient.invalidateQueries({ queryKey: ["network", "interfaces"] });
      }
      prevBridgeStatus = newStatus;

      useBridgeStore.getState().setBridgeState(msg.payload);
      break;
    }
    case "pioneer_status":
      useBridgeStore
        .getState()
        .setPioneerStatus(
          msg.payload.is_receiving,
          msg.payload.last_message_age_ms,
          msg.payload.bridge_connected,
        );
      break;
    case "strata_live":
      useStrataLiveStore
        .getState()
        .setFormula(msg.payload.player_number, msg.payload.formula);
      break;
    case "scan_progress": {
      const status = msg.payload?.status;
      if (status === "completed" || status === "failed") {
        // Terminal state — mark scan complete and refresh caches
        useIngestionStore.getState().setScanComplete(msg.payload);
        queryClient.invalidateQueries({ queryKey: ["tracks"] });
        queryClient.invalidateQueries({ queryKey: ["scanner", "history"] });
      } else {
        useIngestionStore.getState().setScanProgress(msg.payload);
      }
      break;
    }
    case "scan_complete":
      // Backend doesn't currently emit this, but keep for forward compat
      useIngestionStore.getState().setScanComplete(msg.payload);
      queryClient.invalidateQueries({ queryKey: ["tracks"] });
      queryClient.invalidateQueries({ queryKey: ["scanner", "history"] });
      break;
  }
  dispatchToConsole(msg);
}

function onOpen(): void {
  backoff = 1000;
  // Reset mapper diff-detection state so the first messages of the new
  // WS session are treated as fresh — not diffed against pre-disconnect state.
  resetMapperState();
  prevBridgeStatus = null;
  useBridgeStore.getState().setWsConnected(true);
  useConsoleStore.getState().addEntry({
    source: "system",
    severity: "info",
    message: "Connected to backend",
    verbose: false,
  });
}

/** Runtime type guard — validates WS message has required shape before dispatch. */
function isWSMessage(data: unknown): data is WSMessage {
  return (
    typeof data === "object" &&
    data !== null &&
    "type" in data &&
    "payload" in data &&
    typeof (data as Record<string, unknown>).type === "string"
  );
}

function onMessage(event: MessageEvent): void {
  try {
    const parsed: unknown = JSON.parse(event.data);
    if (!isWSMessage(parsed)) return;
    dispatch(parsed);
  } catch {
    // Ignore malformed messages
  }
}

function onClose(): void {
  ws = null;
  useBridgeStore.getState().setWsConnected(false);
  useConsoleStore.getState().addEntry({
    source: "system",
    severity: "error",
    message: "Backend connection lost",
    verbose: false,
  });
  scheduleReconnect();
}

function onError(): void {
  ws?.close();
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, backoff);
  backoff = Math.min(backoff * 2, MAX_BACKOFF);
}

export function connectWebSocket(): void {
  if (ws) return;

  try {
    ws = new WebSocket(WS_URL);
    ws.onopen = onOpen;
    ws.onmessage = onMessage;
    ws.onclose = onClose;
    ws.onerror = onError;
  } catch {
    scheduleReconnect();
  }
}

export function disconnectWebSocket(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.onclose = null; // Prevent reconnect
    ws.close();
    ws = null;
  }
}
