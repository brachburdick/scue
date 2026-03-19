import type { DeviceInfo } from "../../types";
import { useBridgeStore } from "../../stores/bridgeStore";
import { DeviceCard } from "./DeviceCard";

/** Small inline spinner for S4 (starting) state. */
function Spinner() {
  return (
    <svg
      className="inline-block w-4 h-4 animate-spin text-gray-500 ml-1"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

/** Pulsing dot indicator for S6 (recovering) state. */
function PulsingIndicator() {
  return (
    <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse ml-1" />
  );
}

export function DeviceList({
  devices,
}: {
  devices: Record<string, DeviceInfo>;
}) {
  const entries = Object.entries(devices);
  const isReceiving = useBridgeStore((s) => s.isReceiving);
  const lastMessageAgeMs = useBridgeStore((s) => s.lastMessageAgeMs);
  const routeCorrect = useBridgeStore((s) => s.routeCorrect);
  const networkInterface = useBridgeStore((s) => s.networkInterface);
  const status = useBridgeStore((s) => s.status);
  const wsConnected = useBridgeStore((s) => s.wsConnected);

  const isRecovering = useBridgeStore((s) => s.isRecovering);

  if (entries.length > 0) {
    return (
      <div className="space-y-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Devices ({entries.length})
        </h3>
        {entries.map(([ip, device]) => (
          <DeviceCard key={ip} ip={ip} device={device} />
        ))}
      </div>
    );
  }

  // --- Empty state: priority order per spec ---

  // S7: WS disconnected (highest priority)
  if (!wsConnected) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">
          Backend unreachable. Device information unavailable.
        </p>
      </div>
    );
  }

  // S3: crashed
  if (status === "crashed") {
    return (
      <div className="rounded-lg border border-dashed border-red-900/50 px-4 py-6 text-center">
        <p className="text-sm text-red-400/80">
          Bridge crashed. Devices will reappear after restart.
        </p>
      </div>
    );
  }

  // S4: starting
  if (status === "starting") {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">
          Bridge starting. Waiting for device discovery…
          <Spinner />
        </p>
      </div>
    );
  }

  // S5: waiting_for_hardware
  if (status === "waiting_for_hardware") {
    return (
      <div className="rounded-lg border border-dashed border-blue-900/50 px-4 py-6 text-center">
        <p className="text-sm text-blue-400/80">
          Waiting for hardware. Connect Pioneer equipment and adapter.
        </p>
      </div>
    );
  }

  // S6: running (recovering) — uses isRecovering from TASK-006a
  if (isRecovering) {
    return (
      <div className="rounded-lg border border-dashed border-green-900/50 px-4 py-6 text-center">
        <p className="text-sm text-green-400/80">
          Bridge reconnected. Discovering devices on{" "}
          <span className="font-mono">{networkInterface ?? "unknown"}</span>…
          <PulsingIndicator />
        </p>
      </div>
    );
  }

  // S1/S2 existing empty states: recentTraffic vs default
  // Bridge is connected and sending data but beat-link hasn't announced any
  // devices yet. Most likely cause: wrong broadcast route (169.254.255.255
  // going out the wrong interface so Pioneer announcements can't reach the
  // bridge). Also seen briefly after a route fix before beat-link re-probes.
  //
  // "recentTraffic" uses an 8-second grace window on top of isReceiving so
  // the message doesn't flicker between "traffic detected" and "no devices"
  // as Pioneer announcement bursts arrive.
  // lastMessageAgeMs is -1 when no Pioneer packet has ever been received.
  const recentTraffic =
    isReceiving || (lastMessageAgeMs >= 0 && lastMessageAgeMs < 8000);

  if (recentTraffic) {
    return (
      <div className="rounded-lg border border-dashed border-yellow-900/50 px-4 py-5 text-center space-y-1.5">
        <p className="text-sm text-yellow-500/80">
          Pioneer traffic detected on{" "}
          <span className="font-mono text-yellow-400">
            {networkInterface ?? "unknown interface"}
          </span>
          , but no devices discovered yet.
        </p>
        <p className="text-xs text-gray-500">
          {routeCorrect === false
            ? "Route mismatch is likely the cause — fix the route above, then restart the bridge."
            : "Waiting for beat-link device announcements. This usually resolves within a few seconds."}
        </p>
      </div>
    );
  }

  // Default: no devices
  return (
    <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
      <p className="text-sm text-gray-500">
        No Pioneer devices found
        {networkInterface && (
          <span className="text-gray-600">
            {" "}on <span className="font-mono">{networkInterface}</span>
          </span>
        )}
        .
      </p>
      <p className="text-xs text-gray-600 mt-1">
        {routeCorrect === false
          ? "Route mismatch detected — fix the route above, then restart the bridge."
          : "Check cable, interface selection, and route status above."}
      </p>
    </div>
  );
}
