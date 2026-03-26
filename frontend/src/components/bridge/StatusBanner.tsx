import { useBridgeStore } from "../../stores/bridgeStore";

/** Shared spinner SVG used in S4 and S7 narratives. */
function Spinner() {
  return (
    <svg
      className="inline-block w-3 h-3 animate-spin text-current"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

/** Pulsing dot used in S6 (recovering) narrative. */
function PulsingDot() {
  return <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />;
}

interface BannerConfig {
  bg: string;
  dotColor: string;
  textColor: string;
  label: string;
}

const STATUS_CONFIG: Record<string, BannerConfig> = {
  running: { bg: "bg-green-900/50", dotColor: "bg-green-500", textColor: "text-green-400", label: "Bridge: Connected" },
  starting: { bg: "bg-yellow-900/50", dotColor: "bg-yellow-500", textColor: "text-yellow-400", label: "Bridge: Starting" },
  stopped: { bg: "bg-gray-800", dotColor: "bg-gray-500", textColor: "text-gray-400", label: "Bridge: Stopped" },
  crashed: { bg: "bg-red-900/50", dotColor: "bg-red-500", textColor: "text-red-400", label: "Bridge: Crashed" },
  no_jre: { bg: "bg-red-900/50", dotColor: "bg-red-500", textColor: "text-red-400", label: "Java Not Found" },
  no_jar: { bg: "bg-red-900/50", dotColor: "bg-red-500", textColor: "text-red-400", label: "Bridge JAR Missing" },
  fallback: { bg: "bg-yellow-900/50", dotColor: "bg-yellow-500", textColor: "text-yellow-400", label: "Fallback Mode" },
  waiting_for_hardware: { bg: "bg-blue-900/50", dotColor: "bg-blue-500", textColor: "text-blue-400", label: "Bridge: Waiting for Hardware" },
  not_initialized: { bg: "bg-gray-800", dotColor: "bg-gray-500", textColor: "text-gray-400", label: "Not Initialized" },
  ws_disconnected: { bg: "bg-gray-800", dotColor: "bg-gray-500", textColor: "text-gray-400", label: "Backend Unreachable" },
  hw_disconnected: { bg: "bg-orange-900/50", dotColor: "bg-orange-500", textColor: "text-orange-400", label: "Hardware Disconnected" },
};

export function StatusBanner() {
  const status = useBridgeStore((s) => s.status);
  const wsConnected = useBridgeStore((s) => s.wsConnected);
  const isRecovering = useBridgeStore((s) => s.isRecovering);
  const isHwDisconnected = useBridgeStore((s) => s.isHwDisconnected);
  const networkInterface = useBridgeStore((s) => s.networkInterface);
  const devices = useBridgeStore((s) => s.devices);
  const restartAttempt = useBridgeStore((s) => s.restartAttempt);
  const countdownSecondsRemaining = useBridgeStore((s) => s.countdownSecondsRemaining);

  // Priority: WS disconnected > hardware disconnected > bridge status.
  const effectiveKey = !wsConnected
    ? "ws_disconnected"
    : isHwDisconnected
      ? "hw_disconnected"
      : status;
  const config = STATUS_CONFIG[effectiveKey] ?? STATUS_CONFIG.stopped;
  const deviceCount = Object.keys(devices).length;
  const iface = networkInterface ?? "unknown";

  let narrative: React.ReactNode;

  if (!wsConnected) {
    // S7
    narrative = (
      <span className="flex items-center gap-1.5">
        WebSocket connection lost. Reconnecting... <Spinner />
      </span>
    );
  } else if (status === "running" && isRecovering) {
    // S6
    narrative = (
      <span className="flex items-center gap-1.5">
        Bridge reconnected. Discovering devices on {iface}... <PulsingDot />
      </span>
    );
  } else if (status === "running" && isHwDisconnected) {
    // S8: hardware disconnected — running but no devices/traffic for 8s+
    narrative = `Pioneer hardware disconnected from ${iface}. Reconnect a CDJ or DJM to resume.`;
  } else if (status === "running") {
    if (deviceCount > 0) {
      // S1
      narrative = `${deviceCount} device${deviceCount !== 1 ? "s" : ""} on ${iface}`;
    } else {
      // S2
      narrative = `No Pioneer devices on ${iface}. Waiting for hardware announcements.`;
    }
  } else if (status === "crashed") {
    // S3
    const countdownText =
      countdownSecondsRemaining !== null && countdownSecondsRemaining > 0
        ? `Retrying in ${countdownSecondsRemaining}s...`
        : "Restarting...";
    const thresholdWarning =
      restartAttempt === 2
        ? " If next attempt fails, bridge will enter slow-poll mode."
        : "";
    narrative = `Restart attempt ${restartAttempt} of 3. ${countdownText}${thresholdWarning}`;
  } else if (status === "starting") {
    // S4
    narrative = (
      <span className="flex items-center gap-1.5">
        Launching bridge subprocess... <Spinner />
      </span>
    );
  } else if (status === "waiting_for_hardware") {
    // S5
    const countdownText =
      countdownSecondsRemaining !== null && countdownSecondsRemaining > 0
        ? `Checking for hardware in ${countdownSecondsRemaining}s...`
        : "Checking for hardware...";
    narrative = `Crash threshold reached. ${countdownText}`;
  } else {
    // Fallback for other statuses (no_jre, no_jar, stopped, etc.)
    narrative = null;
  }

  return (
    <div className={`rounded-lg px-4 py-3 transition-opacity duration-300 ${config.bg}`}>
      <div className="flex items-center gap-2">
        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${config.dotColor}`} />
        <span className={`text-sm font-medium ${config.textColor}`}>{config.label}</span>
      </div>
      {narrative && (
        <p className="mt-1 ml-[1.125rem] text-xs text-gray-400">{narrative}</p>
      )}
    </div>
  );
}
