import { useBridgeStore } from "../../stores/bridgeStore";

export function TopBar() {
  const dotStatus = useBridgeStore((s) => s.dotStatus);
  const routeWarning = useBridgeStore((s) => s.routeWarning);
  const bridgeStatus = useBridgeStore((s) => s.status);
  const isReceiving = useBridgeStore((s) => s.isReceiving);
  const lastMessageAgeMs = useBridgeStore((s) => s.lastMessageAgeMs);
  const isStartingUp = useBridgeStore((s) => s.isStartingUp);
  const wsConnected = useBridgeStore((s) => s.wsConnected);

  // Build tooltip text
  const tooltip = routeWarning
    ? `Bridge: ${bridgeStatus} | ${routeWarning}`
    : `Bridge: ${bridgeStatus}`;

  const trafficTooltip =
    isReceiving && lastMessageAgeMs >= 0
      ? `Pioneer traffic: active · ${lastMessageAgeMs < 1000 ? `${lastMessageAgeMs}ms ago` : `${(lastMessageAgeMs / 1000).toFixed(1)}s ago`}`
      : "Pioneer traffic: none";

  const startupLabel = !wsConnected
    ? "Connecting..."
    : bridgeStatus === "starting"
      ? "Bridge starting..."
      : null;

  return (
    <header className="h-12 shrink-0 border-b border-gray-800 bg-gray-950 flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold tracking-wide text-white">SCUE</span>
        <span className="text-xs text-gray-500">v0.1.0</span>
      </div>
      <div className="flex items-center gap-4">
        {isStartingUp && startupLabel && (
          <StartupIndicator label={startupLabel} />
        )}
        <span className="text-xs text-gray-500">No project loaded</span>
        {dotStatus !== "disconnected" && (
          <TrafficDot active={isReceiving} title={trafficTooltip} />
        )}
        <StatusDot label="Bridge" status={dotStatus} title={tooltip} />
      </div>
    </header>
  );
}

function StartupIndicator({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full bg-gray-800 px-2.5 py-1" aria-label={`Startup: ${label}`}>
      <svg
        className="w-3 h-3 animate-spin text-gray-400"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span className="text-xs text-gray-400">{label}</span>
    </div>
  );
}

function TrafficDot({ active, title }: { active: boolean; title: string }) {
  return (
    <div className="relative flex items-center" title={title} aria-label={`Pioneer traffic: ${active ? "active" : "none"}`}>
      {active && (
        <span className="absolute inline-flex h-2 w-2 rounded-full bg-cyan-400 opacity-75 animate-ping" />
      )}
      <span
        className={`relative inline-flex h-2 w-2 rounded-full transition-colors duration-300 ${
          active ? "bg-cyan-400" : "bg-gray-700"
        }`}
      />
    </div>
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
    <div className="flex items-center gap-1.5" title={title} aria-label={`Bridge status: ${status}`}>
      <div className={`w-2 h-2 rounded-full ${colors[status]}`} />
      <span className="text-xs text-gray-400">{label}</span>
    </div>
  );
}
