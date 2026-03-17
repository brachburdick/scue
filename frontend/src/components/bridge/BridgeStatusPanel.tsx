import { useBridgeStore } from "../../stores/bridgeStore";
import { StatusBanner } from "./StatusBanner";
import { DeviceList } from "./DeviceList";
import { PlayerList } from "./PlayerList";

export function BridgeStatusPanel() {
  const status = useBridgeStore((s) => s.status);
  const devices = useBridgeStore((s) => s.devices);
  const players = useBridgeStore((s) => s.players);

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-white">Bridge Status</h2>
      <StatusBanner status={status} />
      <DeviceList devices={devices} />
      <PlayerList players={players} />
    </div>
  );
}
