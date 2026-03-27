import { create } from "zustand";
import type { BridgeStatus, DeviceInfo, PlayerInfo, BridgeState } from "../types";

export type DotStatus = "connected" | "disconnected" | "degraded";

/** Statuses considered "non-running" for recovery detection. */
const NON_RUNNING_STATUSES: ReadonlySet<BridgeStatus> = new Set([
  "stopped",
  "starting",
  "crashed",
  "no_jre",
  "no_jar",
  "fallback",
  "waiting_for_hardware",
  "not_initialized",
]);

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
  restartAttempt: number;
  nextRetryInS: number | null;
  routeCorrect: boolean | null;
  routeWarning: string | null;
  devices: Record<string, DeviceInfo>;
  players: Record<string, PlayerInfo>;

  // Pioneer liveness (from WebSocket pioneer_status messages)
  isReceiving: boolean;
  lastMessageAgeMs: number;
  bridgeConnected: boolean;

  // Per-aspect health (from pioneer_status WS messages)
  routeOk: boolean | null;
  devicesCount: number;
  playersCount: number;

  // Last crash reason (from bridge_status)
  lastCrashReason: string | null;

  // Computed status for TopBar StatusDot
  dotStatus: DotStatus;

  // True while WS is not yet connected OR bridge is still launching.
  // Clears once the WS has connected and the bridge reaches a stable state.
  isStartingUp: boolean;

  // Derived: true for 15s after status transitions to "running" from non-running,
  // cleared when devices become non-empty or the timeout expires.
  isRecovering: boolean;

  // Derived: client-side countdown from nextRetryInS, decrements every 1s.
  // null when no countdown is active.
  countdownSecondsRemaining: number | null;

  // Derived: true when status is "running" but devices are empty and
  // isReceiving is false for more than 8 seconds. Indicates likely hardware
  // disconnect after a period of normal operation.
  isHwDisconnected: boolean;

  // Actions
  setWsConnected: (connected: boolean) => void;
  setBridgeState: (state: BridgeState) => void;
  setPioneerStatus: (isReceiving: boolean, ageMs: number, bridgeConnected: boolean, routeOk?: boolean | null, devicesCount?: number, playersCount?: number) => void;
}

function computeDotStatus(wsConnected: boolean, status: BridgeStatus): DotStatus {
  if (!wsConnected) return "disconnected";
  if (status === "running") return "connected";
  if (status === "fallback" || status === "waiting_for_hardware") return "degraded";
  return "disconnected";
}

/** Startup is in progress until WS is open AND bridge has left "starting". */
function computeIsStartingUp(wsConnected: boolean, status: BridgeStatus): boolean {
  return !wsConnected || status === "starting";
}

// --- Timer management for isRecovering and countdownSecondsRemaining ---

let recoveryTimer: ReturnType<typeof setTimeout> | null = null;
let countdownInterval: ReturnType<typeof setInterval> | null = null;
let hwDisconnectTimer: ReturnType<typeof setTimeout> | null = null;

function clearRecoveryTimer(): void {
  if (recoveryTimer !== null) {
    clearTimeout(recoveryTimer);
    recoveryTimer = null;
  }
}

function clearCountdownInterval(): void {
  if (countdownInterval !== null) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }
}

function clearHwDisconnectTimer(): void {
  if (hwDisconnectTimer !== null) {
    clearTimeout(hwDisconnectTimer);
    hwDisconnectTimer = null;
  }
}

function startHwDisconnectTimer(): void {
  clearHwDisconnectTimer();
  hwDisconnectTimer = setTimeout(() => {
    hwDisconnectTimer = null;
    useBridgeStore.setState({ isHwDisconnected: true });
  }, 8_000);
}

/** Evaluate whether the hw-disconnect timer should be running or cleared. */
function updateHwDisconnectState(
  status: BridgeStatus,
  devices: Record<string, DeviceInfo>,
  isReceiving: boolean,
): void {
  const isRunning = status === "running";
  const hasDevices = Object.keys(devices).length > 0;

  if (isRunning && !hasDevices && !isReceiving) {
    // Condition met — start timer if not already running.
    if (hwDisconnectTimer === null && !useBridgeStore.getState().isHwDisconnected) {
      startHwDisconnectTimer();
    }
  } else {
    // Condition no longer met — clear timer and flag.
    clearHwDisconnectTimer();
    if (useBridgeStore.getState().isHwDisconnected) {
      useBridgeStore.setState({ isHwDisconnected: false });
    }
  }
}

function startRecoveryTimer(): void {
  clearRecoveryTimer();
  recoveryTimer = setTimeout(() => {
    recoveryTimer = null;
    useBridgeStore.setState({ isRecovering: false });
  }, 15_000);
}

function startCountdown(initialSeconds: number): void {
  clearCountdownInterval();
  useBridgeStore.setState({ countdownSecondsRemaining: initialSeconds });
  countdownInterval = setInterval(() => {
    const current = useBridgeStore.getState().countdownSecondsRemaining;
    if (current === null || current <= 1) {
      clearCountdownInterval();
      useBridgeStore.setState({ countdownSecondsRemaining: 0 });
    } else {
      useBridgeStore.setState({ countdownSecondsRemaining: current - 1 });
    }
  }, 1_000);
}

export const useBridgeStore = create<BridgeStoreState>((set) => ({
  wsConnected: false,
  status: "stopped",
  port: 0,
  networkInterface: null,
  jarExists: false,
  jreAvailable: false,
  restartCount: 0,
  restartAttempt: 0,
  nextRetryInS: null,
  routeCorrect: null,
  routeWarning: null,
  devices: {},
  players: {},
  isReceiving: false,
  lastMessageAgeMs: -1,
  bridgeConnected: false,
  routeOk: null,
  devicesCount: 0,
  playersCount: 0,
  lastCrashReason: null,
  dotStatus: "disconnected",
  isStartingUp: true,
  isRecovering: false,
  countdownSecondsRemaining: null,
  isHwDisconnected: false,

  setWsConnected: (connected: boolean) =>
    set((prev) => {
      if (!connected) {
        // WS disconnected — clear all timers and recovery state.
        clearRecoveryTimer();
        clearCountdownInterval();
        clearHwDisconnectTimer();
      }
      const newStatus = connected ? prev.status : "not_initialized";
      return {
        wsConnected: connected,
        isStartingUp: computeIsStartingUp(connected, newStatus),
        dotStatus: computeDotStatus(connected, newStatus),
        // Clear stale device/player data and status on WS disconnect so
        // components show empty state instead of last-known values.
        ...(connected
          ? {}
          : {
              status: "not_initialized" as BridgeStatus,
              devices: {},
              players: {},
              isRecovering: false,
              countdownSecondsRemaining: null,
              isHwDisconnected: false,
            }),
      };
    }),

  setBridgeState: (state: BridgeState) => {
    set((prev) => {
      const isRunning = state.status === "running";
      const wasNonRunning = NON_RUNNING_STATUSES.has(prev.status);
      // Keep devices/players during "starting" if we were previously running
      // (e.g. during uvicorn --reload restart). Clear on terminal states.
      const isRestarting = state.status === "starting" && prev.status === "running";
      const devices = isRunning
        ? state.devices
        : isRestarting
          ? prev.devices
          : {};
      const hasDevices = Object.keys(devices).length > 0;

      // --- isRecovering logic ---
      let isRecovering = prev.isRecovering;

      if (isRunning && wasNonRunning) {
        // Entering running from non-running: start recovery window.
        if (hasDevices) {
          // Devices already present — no recovery needed.
          isRecovering = false;
          clearRecoveryTimer();
        } else {
          isRecovering = true;
          startRecoveryTimer();
        }
      } else if (isRecovering && hasDevices) {
        // Devices arrived during recovery window — clear.
        isRecovering = false;
        clearRecoveryTimer();
      } else if (!isRunning) {
        // Left running state — clear recovery.
        isRecovering = false;
        clearRecoveryTimer();
      }

      // --- countdownSecondsRemaining logic ---
      if (state.status !== prev.status) {
        // Status changed — reset countdown. If new status has nextRetryInS,
        // a new countdown will start below.
        clearCountdownInterval();
      }

      if (
        state.next_retry_in_s !== null &&
        state.next_retry_in_s > 0 &&
        (state.status === "crashed" || state.status === "waiting_for_hardware")
      ) {
        startCountdown(state.next_retry_in_s);
      } else if (state.status !== "crashed" && state.status !== "waiting_for_hardware") {
        clearCountdownInterval();
      }

      return {
        status: state.status,
        port: state.port,
        networkInterface: state.network_interface,
        jarExists: state.jar_exists,
        jreAvailable: state.jre_available,
        restartCount: state.restart_count,
        restartAttempt: state.restart_attempt,
        nextRetryInS: state.next_retry_in_s,
        routeCorrect: state.route_correct,
        routeWarning: state.route_warning,
        devices,
        players: isRunning ? state.players : isRestarting ? prev.players : {},
        lastCrashReason: state.last_crash_reason ?? prev.lastCrashReason,
        dotStatus: computeDotStatus(prev.wsConnected, state.status),
        isStartingUp: computeIsStartingUp(prev.wsConnected, state.status),
        isRecovering,
      };
    });
    // Post-set: evaluate hw-disconnect timer with committed state.
    const s = useBridgeStore.getState();
    updateHwDisconnectState(s.status, s.devices, s.isReceiving);
  },

  setPioneerStatus: (isReceiving: boolean, ageMs: number, bridgeConnected: boolean, routeOk?: boolean | null, devicesCount?: number, playersCount?: number) => {
    set((prev) => ({
      isReceiving,
      lastMessageAgeMs: ageMs,
      bridgeConnected,
      ...(routeOk !== undefined ? { routeOk } : {}),
      ...(devicesCount !== undefined ? { devicesCount } : {}),
      ...(playersCount !== undefined ? { playersCount } : {}),
      dotStatus: computeDotStatus(prev.wsConnected, prev.status),
    }));
    // Post-set: pioneer liveness changes affect hw-disconnect detection.
    const s = useBridgeStore.getState();
    updateHwDisconnectState(s.status, s.devices, s.isReceiving);
  },
}));
