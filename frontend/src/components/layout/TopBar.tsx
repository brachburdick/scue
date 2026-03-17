import { useBridgeStore } from "../../stores/bridgeStore";

export function TopBar() {
  const dotStatus = useBridgeStore((s) => s.dotStatus);
  const routeWarning = useBridgeStore((s) => s.routeWarning);
  const bridgeStatus = useBridgeStore((s) => s.status);

  // Build tooltip text
  const tooltip = routeWarning
    ? `Bridge: ${bridgeStatus} | ${routeWarning}`
    : `Bridge: ${bridgeStatus}`;

  return (
    <header className="h-12 shrink-0 border-b border-gray-800 bg-gray-950 flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold tracking-wide text-white">SCUE</span>
        <span className="text-xs text-gray-500">v0.1.0</span>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-xs text-gray-500">No project loaded</span>
        <StatusDot label="Bridge" status={dotStatus} title={tooltip} />
      </div>
    </header>
  );
}

function StatusDot({
  label,
  status,
  title,
}: {
  label: string;
  status: "connected" | "disconnected" | "degraded";
  title?: string;
}) {
  const colors = {
    connected: "bg-green-500",
    disconnected: "bg-gray-600",
    degraded: "bg-yellow-500",
  };
  return (
    <div className="flex items-center gap-1.5" title={title}>
      <div className={`w-2 h-2 rounded-full ${colors[status]}`} />
      <span className="text-xs text-gray-400">{label}</span>
    </div>
  );
}
