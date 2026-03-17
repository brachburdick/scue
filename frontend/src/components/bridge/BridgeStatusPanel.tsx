import { useBridgeStore } from "../../stores/bridgeStore";
import { StatusBanner } from "./StatusBanner";
import { DeviceList } from "./DeviceList";
import { PlayerList } from "./PlayerList";

function TrafficIndicator() {
  const isReceiving = useBridgeStore((s) => s.isReceiving);
  const ageMs = useBridgeStore((s) => s.lastMessageAgeMs);
  const status = useBridgeStore((s) => s.status);

  if (status !== "running" && status !== "fallback") return null;

  const ageLabel =
    ageMs < 0
      ? "no data"
      : ageMs < 1000
        ? `${ageMs}ms ago`
        : `${(ageMs / 1000).toFixed(1)}s ago`;

  return (
    <div className="flex items-center gap-2 rounded-md bg-gray-800/60 px-3 py-2">
      <div
        className={`w-2 h-2 rounded-full ${
          isReceiving ? "bg-green-400 animate-pulse" : "bg-gray-600"
        }`}
      />
      <span className="text-xs text-gray-400">
        Pioneer traffic:{" "}
        <span className={isReceiving ? "text-green-400" : "text-gray-500"}>
          {isReceiving ? `active · ${ageLabel}` : "none"}
        </span>
      </span>
    </div>
  );
}

export function BridgeStatusPanel() {
  const status = useBridgeStore((s) => s.status);
  const devices = useBridgeStore((s) => s.devices);
  const players = useBridgeStore((s) => s.players);

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-white">Bridge Status</h2>
      <StatusBanner status={status} />
      <TrafficIndicator />
      <DeviceList devices={devices} />
      <PlayerList players={players} />
    </div>
  );
}
