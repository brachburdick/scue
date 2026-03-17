import { create } from "zustand";
import type { BridgeStatus, DeviceInfo, PlayerInfo, BridgeState } from "../types";

export type DotStatus = "connected" | "disconnected" | "degraded";

interface BridgeStoreState {
  // WebSocket connection state
  wsConnected: boolean;

  // Bridge state (from WebSocket bridge_status messages)
  status: BridgeStatus;
  port: number;
  networkInterface: string | null;
  jarExists: boolean;
  jreAvailable: boolean;
  restartCount: number;
  routeCorrect: boolean | null;
  routeWarning: string | null;
  devices: Record<string, DeviceInfo>;
  players: Record<string, PlayerInfo>;

  // Pioneer liveness (from WebSocket pioneer_status messages)
  isReceiving: boolean;
  lastMessageAgeMs: number;

  // Computed status for TopBar StatusDot
  dotStatus: DotStatus;

  // True while WS is not yet connected OR bridge is still launching.
  // Clears once the WS has connected and the bridge reaches a stable state.
  isStartingUp: boolean;

  // Actions
  setWsConnected: (connected: boolean) => void;
  setBridgeState: (state: BridgeState) => void;
  setPioneerStatus: (isReceiving: boolean, ageMs: number) => void;
}

function computeDotStatus(status: BridgeStatus): DotStatus {
  if (status === "running") return "connected";
  if (status === "fallback") return "degraded";
  return "disconnected";
}

/** Startup is in progress until WS is open AND bridge has left "starting". */
function computeIsStartingUp(wsConnected: boolean, status: BridgeStatus): boolean {
  return !wsConnected || status === "starting";
}

export const useBridgeStore = create<BridgeStoreState>((set) => ({
  wsConnected: false,
  status: "stopped",
  port: 0,
  networkInterface: null,
  jarExists: false,
  jreAvailable: false,
  restartCount: 0,
  routeCorrect: null,
  routeWarning: null,
  devices: {},
  players: {},
  isReceiving: false,
  lastMessageAgeMs: -1,
  dotStatus: "disconnected",
  isStartingUp: true,

  setWsConnected: (connected: boolean) =>
    set((prev) => ({
      wsConnected: connected,
      isStartingUp: computeIsStartingUp(connected, prev.status),
    })),

  setBridgeState: (state: BridgeState) =>
    set((prev) => ({
      status: state.status,
      port: state.port,
      networkInterface: state.network_interface,
      jarExists: state.jar_exists,
      jreAvailable: state.jre_available,
      restartCount: state.restart_count,
      routeCorrect: state.route_correct,
      routeWarning: state.route_warning,
      devices: state.devices,
      players: state.players,
      dotStatus: computeDotStatus(state.status),
      isStartingUp: computeIsStartingUp(prev.wsConnected, state.status),
    })),

  setPioneerStatus: (isReceiving: boolean, ageMs: number) =>
    set((prev) => ({
      isReceiving,
      lastMessageAgeMs: ageMs,
      dotStatus: computeDotStatus(prev.status),
    })),
}));
