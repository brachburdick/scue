import { useState } from "react";
import { InterfaceSelector } from "./InterfaceSelector";
import { RouteStatusBanner } from "./RouteStatusBanner";
import { ActionBar } from "./ActionBar";

export function HardwareSelectionPanel() {
  const [pendingChanges, setPendingChanges] = useState(false);

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-white">Hardware Selection</h2>
      <InterfaceSelector onInterfaceChanged={() => setPendingChanges(true)} />
      <RouteStatusBanner />
      <ActionBar pendingChanges={pendingChanges} />
    </div>
  );
}
