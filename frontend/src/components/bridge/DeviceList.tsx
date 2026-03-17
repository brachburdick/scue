import type { DeviceInfo } from "../../types";
import { DeviceCard } from "./DeviceCard";

export function DeviceList({
  devices,
}: {
  devices: Record<string, DeviceInfo>;
}) {
  const entries = Object.entries(devices);

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">
          No Pioneer devices found. Check cable, interface, and route.
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
