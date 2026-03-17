import type { DeviceInfo } from "../../types";
import { useBridgeStore } from "../../stores/bridgeStore";
import { DeviceCard } from "./DeviceCard";

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

  if (entries.length === 0) {
    // Bridge is connected and sending data but beat-link hasn't announced any
    // devices yet. Most likely cause: wrong broadcast route (169.254.255.255
    // going out the wrong interface so Pioneer announcements can't reach the
    // bridge). Also seen briefly after a route fix before beat-link re-probes.
    //
    // Note: USB-to-Ethernet adapters (en4, en5, en16, etc.) are handled the
    // same as built-in ports — the route and interface selection matter, not
    // the adapter type. If devices still don't appear after fixing the route,
    // unplug and replug the adapter to trigger a fresh DHCP + link-local cycle.
    //
    // "recentTraffic" uses an 8-second grace window on top of isReceiving so
    // the message doesn't flicker between "traffic detected" and "no devices"
    // as Pioneer announcement bursts arrive — the watchdog pulses isReceiving
    // true/false between bursts, but lastMessageAgeMs stays low while traffic
    // is ongoing.
    // lastMessageAgeMs is -1 when no Pioneer packet has ever been received.
    // A non-negative value below 8 000 ms means traffic arrived recently.
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
