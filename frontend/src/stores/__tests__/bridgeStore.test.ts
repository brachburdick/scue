import { describe, it, expect, beforeEach } from "vitest";
import { useBridgeStore } from "../bridgeStore";
import type { BridgeState, BridgeStatus } from "../../types";

/** Reset the store to initial state before each test. */
function resetStore() {
  useBridgeStore.setState({
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
  });
}

function makeBridgeState(overrides: Partial<BridgeState> = {}): BridgeState {
  return {
    status: "running",
    port: 17400,
    network_interface: "en0",
    jar_path: "/path/to/jar",
    jar_exists: true,
    jre_available: true,
    restart_count: 0,
    restart_attempt: 0,
    next_retry_in_s: null,
    route_correct: true,
    route_warning: null,
    route_competing_interfaces: [],
    last_crash_reason: null,
    devices: {},
    players: {},
    ...overrides,
  };
}

describe("bridgeStore", () => {
  beforeEach(resetStore);

  describe("initial state", () => {
    it("starts disconnected with no devices/players", () => {
      const state = useBridgeStore.getState();
      expect(state.wsConnected).toBe(false);
      expect(state.status).toBe("stopped");
      expect(state.dotStatus).toBe("disconnected");
      expect(state.isStartingUp).toBe(true);
      expect(state.isReceiving).toBe(false);
      expect(Object.keys(state.devices)).toHaveLength(0);
      expect(Object.keys(state.players)).toHaveLength(0);
    });
  });

  describe("setWsConnected", () => {
    it("updates wsConnected and recomputes isStartingUp", () => {
      useBridgeStore.getState().setWsConnected(true);
      const state = useBridgeStore.getState();
      expect(state.wsConnected).toBe(true);
      // status is still "stopped" so isStartingUp depends on that
      // !wsConnected || status === "starting" → false || false → false
      expect(state.isStartingUp).toBe(false);
    });

    it("WS connected + status starting = still starting up", () => {
      // First set status to "starting"
      useBridgeStore.getState().setBridgeState(makeBridgeState({ status: "starting" }));
      useBridgeStore.getState().setWsConnected(true);
      const state = useBridgeStore.getState();
      expect(state.wsConnected).toBe(true);
      expect(state.isStartingUp).toBe(true);
    });

    it("disconnecting sets isStartingUp back to true", () => {
      useBridgeStore.getState().setWsConnected(true);
      expect(useBridgeStore.getState().isStartingUp).toBe(false);

      useBridgeStore.getState().setWsConnected(false);
      expect(useBridgeStore.getState().isStartingUp).toBe(true);
    });
  });

  describe("setBridgeState", () => {
    it("updates all bridge fields from a BridgeState message", () => {
      const devices = {
        "169.254.20.101": {
          device_name: "XDJ-AZ",
          device_number: 1,
          device_type: "cdj" as const,
          uses_dlp: true,
        },
      };
      const players = {
        "1": {
          bpm: 128,
          pitch: 0,
          playback_state: "playing",
          is_on_air: true,
          rekordbox_id: 42001,
          beat_within_bar: 1,
          track_type: "rekordbox",
          playback_position_ms: 5000,
          track_source_player: 1,
          track_source_slot: "usb",
        },
      };

      useBridgeStore.getState().setBridgeState(
        makeBridgeState({ devices, players, restart_count: 3 })
      );

      const state = useBridgeStore.getState();
      expect(state.status).toBe("running");
      expect(state.port).toBe(17400);
      expect(state.networkInterface).toBe("en0");
      expect(state.jarExists).toBe(true);
      expect(state.jreAvailable).toBe(true);
      expect(state.restartCount).toBe(3);
      expect(state.routeCorrect).toBe(true);
      expect(Object.keys(state.devices)).toHaveLength(1);
      expect(state.devices["169.254.20.101"].device_name).toBe("XDJ-AZ");
      expect(Object.keys(state.players)).toHaveLength(1);
      expect(state.players["1"].bpm).toBe(128);
    });

    it("computes dotStatus from bridge status", () => {
      const cases: [BridgeStatus, string][] = [
        ["running", "connected"],
        ["fallback", "degraded"],
        ["stopped", "disconnected"],
        ["crashed", "disconnected"],
        ["starting", "disconnected"],
        ["no_jre", "disconnected"],
        ["no_jar", "disconnected"],
      ];

      for (const [status, expected] of cases) {
        useBridgeStore.getState().setBridgeState(makeBridgeState({ status }));
        expect(useBridgeStore.getState().dotStatus).toBe(expected);
        resetStore();
      }
    });

    it("recomputes isStartingUp when status transitions to running", () => {
      // WS connected + status starting = starting up
      useBridgeStore.getState().setWsConnected(true);
      useBridgeStore.getState().setBridgeState(makeBridgeState({ status: "starting" }));
      expect(useBridgeStore.getState().isStartingUp).toBe(true);

      // Status transitions to running → no longer starting up
      useBridgeStore.getState().setBridgeState(makeBridgeState({ status: "running" }));
      expect(useBridgeStore.getState().isStartingUp).toBe(false);
    });
  });

  describe("setPioneerStatus", () => {
    it("updates isReceiving and lastMessageAgeMs", () => {
      useBridgeStore.getState().setPioneerStatus(true, 150, true);
      const state = useBridgeStore.getState();
      expect(state.isReceiving).toBe(true);
      expect(state.lastMessageAgeMs).toBe(150);
    });

    it("does not change dotStatus (driven by bridge status only)", () => {
      useBridgeStore.getState().setBridgeState(makeBridgeState({ status: "running" }));
      expect(useBridgeStore.getState().dotStatus).toBe("connected");

      // Pioneer status goes to not-receiving — dot should stay green
      useBridgeStore.getState().setPioneerStatus(false, 5000, true);
      expect(useBridgeStore.getState().dotStatus).toBe("connected");
    });
  });

  describe("state isolation", () => {
    it("device and player updates don't clobber each other", () => {
      // Set devices
      useBridgeStore.getState().setBridgeState(
        makeBridgeState({
          devices: {
            "169.254.20.101": {
              device_name: "XDJ-AZ",
              device_number: 1,
              device_type: "cdj",
              uses_dlp: true,
            },
          },
          players: {
            "1": {
              bpm: 128,
              pitch: 0,
              playback_state: "playing",
              is_on_air: true,
              rekordbox_id: 42001,
              beat_within_bar: 1,
              track_type: "rekordbox",
              playback_position_ms: 5000,
              track_source_player: 1,
              track_source_slot: "usb",
            },
          },
        })
      );

      // Update pioneer status — devices/players should remain
      useBridgeStore.getState().setPioneerStatus(true, 100, true);

      const state = useBridgeStore.getState();
      expect(Object.keys(state.devices)).toHaveLength(1);
      expect(Object.keys(state.players)).toHaveLength(1);
      expect(state.isReceiving).toBe(true);
    });

    it("setWsConnected doesn't clear bridge state", () => {
      useBridgeStore.getState().setBridgeState(makeBridgeState({ status: "running" }));
      useBridgeStore.getState().setWsConnected(false);

      // Bridge state fields should remain (only wsConnected + isStartingUp change)
      const state = useBridgeStore.getState();
      expect(state.status).toBe("running");
      expect(state.port).toBe(17400);
    });
  });
});
