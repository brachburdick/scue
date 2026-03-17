import { BridgeStatusPanel } from "../components/bridge/BridgeStatusPanel";
import { HardwareSelectionPanel } from "../components/bridge/HardwareSelectionPanel";

export function BLTPage() {
  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Beat-Link Transport</h1>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <BridgeStatusPanel />
        <HardwareSelectionPanel />
      </div>
    </div>
  );
}
