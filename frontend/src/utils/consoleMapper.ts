/** Maps incoming WS messages to ConsoleEntry objects for the console panel.
 *
 * Tracks previous state at module level for diff detection (Clean mode).
 * Safe because there is exactly one WS connection (singleton).
 */

import type { WSMessage } from "../types/ws";
import type { ConsoleEntry, ConsoleSource, ConsoleSeverity } from "../types/console";
import type { BridgeStatus } from "../types/bridge";

// ---------- Previous-state tracking for diff detection ----------

let prevBridgeStatus: BridgeStatus | null = null;
let prevIsReceiving: boolean | null = null;
let prevBridgeConnected: boolean | null = null;
let prevDeviceKeys: string[] = [];
let prevRestartCount: number = 0;
let prevRouteWarning: string | null = null;
let prevJarExists: boolean | null = null;
let prevJreAvailable: boolean | null = null;

/** Reset all tracked state. Exposed for test isolation. */
export function resetMapperState(): void {
  prevBridgeStatus = null;
  prevIsReceiving = null;
  prevBridgeConnected = null;
  prevDeviceKeys = [];
  prevRestartCount = 0;
  prevRouteWarning = null;
  prevJarExists = null;
  prevJreAvailable = null;
}

// ---------- Helpers ----------

type PartialEntry = Omit<ConsoleEntry, "id" | "timestamp">;

function clean(
  source: ConsoleSource,
  severity: ConsoleSeverity,
  message: string,
  raw?: unknown,
): PartialEntry {
  return { source, severity, message, verbose: false, raw };
}

function verbose(
  source: ConsoleSource,
  severity: ConsoleSeverity,
  message: string,
  raw?: unknown,
): PartialEntry {
  return { source, severity, message, verbose: true, raw };
}

function severityForStatus(status: BridgeStatus): ConsoleSeverity {
  if (status === "crashed" || status === "no_jre" || status === "no_jar") return "error";
  if (status === "fallback" || status === "waiting_for_hardware") return "warn";
  return "info";
}

// ---------- Bridge status mapping ----------

function mapBridgeStatus(payload: WSMessage & { type: "bridge_status" }): PartialEntry[] {
  const s = payload.payload;
  const entries: PartialEntry[] = [];

  // --- Clean entries (diff detection) ---

  // Status change
  if (prevBridgeStatus !== null && s.status !== prevBridgeStatus) {
    const sev = severityForStatus(s.status);
    let msg = `Bridge ${prevBridgeStatus} \u2192 ${s.status}`;
    if (s.status === "running" && s.network_interface) {
      msg = `Bridge connected on ${s.network_interface} (port ${s.port})`;
    } else if (s.status === "crashed") {
      const retryPart = s.next_retry_in_s !== null ? `, retry in ${s.next_retry_in_s}s` : "";
      msg = `Bridge crashed (restart ${s.restart_count}/3${retryPart})`;
    } else if (s.status === "waiting_for_hardware") {
      msg = "Bridge waiting for hardware (polling every 30s)";
    } else if (s.status === "fallback") {
      msg = "Bridge entered fallback mode";
    }
    entries.push(clean("bridge", sev, msg));
  } else if (prevBridgeStatus === null && s.status !== "stopped") {
    // First message with non-default status
    entries.push(clean("bridge", severityForStatus(s.status), `Bridge status: ${s.status}`));
  }

  // Device discovery changes
  const currentDeviceKeys = Object.keys(s.devices).sort();
  if (prevBridgeStatus !== null) {
    const added = currentDeviceKeys.filter((k) => !prevDeviceKeys.includes(k));
    const removed = prevDeviceKeys.filter((k) => !currentDeviceKeys.includes(k));
    for (const k of added) {
      const d = s.devices[k];
      entries.push(clean("bridge", "info", `Device discovered: ${d.device_name} (#${d.device_number})`));
    }
    for (const k of removed) {
      entries.push(clean("bridge", "warn", `Device lost: ${k}`));
    }
  }

  // Restart count increase
  if (prevRestartCount !== null && s.restart_count > prevRestartCount) {
    entries.push(clean("bridge", "warn", `Bridge restarted (count: ${s.restart_count})`));
  }

  // Route warning change
  if (s.route_warning !== prevRouteWarning && s.route_warning !== null) {
    entries.push(clean("bridge", "warn", `Route warning: ${s.route_warning}`));
  }

  // JAR/JRE availability changes
  if (prevJarExists !== null && s.jar_exists !== prevJarExists && !s.jar_exists) {
    entries.push(clean("bridge", "error", "Bridge JAR not found"));
  }
  if (prevJreAvailable !== null && s.jre_available !== prevJreAvailable && !s.jre_available) {
    entries.push(clean("bridge", "error", "Java runtime not available"));
  }

  // --- Verbose entry (every message) ---
  const deviceCount = Object.keys(s.devices).length;
  const playerCount = Object.keys(s.players).length;
  entries.push(
    verbose(
      "bridge",
      "info",
      `bridge_status: ${s.status}, ${deviceCount} devices, ${playerCount} players`,
      s,
    ),
  );

  // --- Update previous state ---
  prevBridgeStatus = s.status;
  prevDeviceKeys = currentDeviceKeys;
  prevRestartCount = s.restart_count;
  prevRouteWarning = s.route_warning;
  prevJarExists = s.jar_exists;
  prevJreAvailable = s.jre_available;

  return entries;
}

// ---------- Pioneer status mapping ----------

function mapPioneerStatus(payload: WSMessage & { type: "pioneer_status" }): PartialEntry[] {
  const s = payload.payload;
  const entries: PartialEntry[] = [];

  // --- Clean entries (transition detection) ---
  if (prevIsReceiving !== null && s.is_receiving !== prevIsReceiving) {
    if (s.is_receiving) {
      entries.push(clean("pioneer", "info", "Pioneer traffic resumed"));
    } else {
      entries.push(clean("pioneer", "warn", "Pioneer traffic lost"));
    }
  }

  if (prevBridgeConnected !== null && s.bridge_connected !== prevBridgeConnected) {
    if (s.bridge_connected) {
      entries.push(clean("pioneer", "info", "Bridge connection restored"));
    } else {
      entries.push(clean("pioneer", "error", "Bridge connection lost"));
    }
  }

  // --- Verbose entry (every message) ---
  entries.push(
    verbose(
      "pioneer",
      "info",
      `pioneer_status: receiving=${s.is_receiving}, age=${s.last_message_age_ms}ms`,
      s,
    ),
  );

  // --- Update previous state ---
  prevIsReceiving = s.is_receiving;
  prevBridgeConnected = s.bridge_connected;

  return entries;
}

// ---------- Public API ----------

/** Convert a WS message into zero or more console entries. */
export function mapWSMessageToEntries(msg: WSMessage): PartialEntry[] {
  switch (msg.type) {
    case "bridge_status":
      return mapBridgeStatus(msg);
    case "pioneer_status":
      return mapPioneerStatus(msg);
    default:
      return [];
  }
}
