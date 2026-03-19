import type { ConsoleEntry } from "../../types/console";

/** Format a timestamp as HH:MM:SS.mmm */
function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

const SOURCE_LABELS: Record<ConsoleEntry["source"], string> = {
  bridge: "BRG",
  pioneer: "PIO",
  system: "SYS",
};

const SOURCE_STYLES: Record<ConsoleEntry["source"], string> = {
  bridge: "bg-blue-900 text-blue-300",
  pioneer: "bg-cyan-900 text-cyan-300",
  system: "bg-gray-700 text-gray-300",
};

const SEVERITY_DOT_COLOR: Record<ConsoleEntry["severity"], string> = {
  info: "text-gray-500",
  warn: "text-yellow-500",
  error: "text-red-500",
};

const MESSAGE_COLOR: Record<ConsoleEntry["severity"], string> = {
  info: "text-gray-400",
  warn: "text-yellow-400",
  error: "text-red-400",
};

interface LogEntryProps {
  entry: ConsoleEntry;
}

export function LogEntry({ entry }: LogEntryProps) {
  return (
    <div className="flex items-center gap-2 px-4 py-0.5 font-mono text-xs hover:bg-gray-900 whitespace-nowrap">
      {/* Timestamp */}
      <span className="text-gray-600 shrink-0">{formatTimestamp(entry.timestamp)}</span>

      {/* Source badge */}
      <span
        className={`px-1.5 py-0 rounded text-[10px] leading-4 shrink-0 ${SOURCE_STYLES[entry.source]}`}
      >
        {SOURCE_LABELS[entry.source]}
      </span>

      {/* Severity dot */}
      <span className={`shrink-0 ${SEVERITY_DOT_COLOR[entry.severity]}`}>{"\u25CF"}</span>

      {/* Message */}
      <span className={MESSAGE_COLOR[entry.severity]}>{entry.message}</span>
    </div>
  );
}
