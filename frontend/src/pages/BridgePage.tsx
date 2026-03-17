import { BridgeStatusPanel } from "../components/bridge/BridgeStatusPanel";
import { HardwareSelectionPanel } from "../components/bridge/HardwareSelectionPanel";

export function BridgePage() {
  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Bridge</h1>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <BridgeStatusPanel />
        <HardwareSelectionPanel />
      </div>
    </div>
  );
}
