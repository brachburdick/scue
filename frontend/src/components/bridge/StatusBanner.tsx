import type { BridgeStatus } from "../../types";

const STATUS_CONFIG: Record<
  string,
  { bg: string; text: string; label: string }
> = {
  running: { bg: "bg-green-900/50", text: "text-green-400", label: "Connected" },
  starting: { bg: "bg-yellow-900/50", text: "text-yellow-400", label: "Starting..." },
  stopped: { bg: "bg-gray-800", text: "text-gray-400", label: "Stopped" },
  crashed: { bg: "bg-red-900/50", text: "text-red-400", label: "Crashed" },
  no_jre: { bg: "bg-red-900/50", text: "text-red-400", label: "Java Not Found" },
  no_jar: { bg: "bg-red-900/50", text: "text-red-400", label: "Bridge JAR Missing" },
  fallback: { bg: "bg-yellow-900/50", text: "text-yellow-400", label: "Fallback Mode" },
  not_initialized: { bg: "bg-gray-800", text: "text-gray-400", label: "Not Initialized" },
};

export function StatusBanner({ status }: { status: BridgeStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.stopped;

  return (
    <div className={`rounded-lg px-4 py-3 ${config.bg}`}>
      <div className="flex items-center gap-2">
        <div
          className={`w-2.5 h-2.5 rounded-full ${
            status === "running"
              ? "bg-green-500"
              : status === "crashed" || status === "no_jre" || status === "no_jar"
                ? "bg-red-500"
                : status === "starting" || status === "fallback"
                  ? "bg-yellow-500"
                  : "bg-gray-500"
          }`}
        />
        <span className={`text-sm font-medium ${config.text}`}>
          Bridge: {config.label}
        </span>
      </div>
    </div>
  );
}
