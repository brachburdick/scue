import { create } from "zustand";
import type { BridgeStatus, DeviceInfo, PlayerInfo, BridgeState } from "../types";

export type DotStatus = "connected" | "disconnected" | "degraded";

interface BridgeStoreState {
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

  // Actions
  setBridgeState: (state: BridgeState) => void;
  setPioneerStatus: (isReceiving: boolean, ageMs: number) => void;
}

function computeDotStatus(
  status: BridgeStatus,
  isReceiving: boolean,
): DotStatus {
  if (status === "running" && isReceiving) return "connected";
  if (status === "running" || status === "fallback") return "degraded";
  return "disconnected";
}

export const useBridgeStore = create<BridgeStoreState>((set) => ({
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
      dotStatus: computeDotStatus(state.status, prev.isReceiving),
    })),

  setPioneerStatus: (isReceiving: boolean, ageMs: number) =>
    set((prev) => ({
      isReceiving,
      lastMessageAgeMs: ageMs,
      dotStatus: computeDotStatus(prev.status, isReceiving),
    })),
}));
