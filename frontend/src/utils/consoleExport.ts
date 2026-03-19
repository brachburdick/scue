/** Export console entries as a downloadable .log file. */

import type { ConsoleEntry } from "../types/console";

const SOURCE_LABELS: Record<ConsoleEntry["source"], string> = {
  bridge: "BRG",
  pioneer: "PIO",
  system: "SYS",
};

const SEVERITY_LABELS: Record<ConsoleEntry["severity"], string> = {
  info: "INFO ",
  warn: "WARN ",
  error: "ERROR",
};

function formatEntryForExport(entry: ConsoleEntry): string {
  const ts = new Date(entry.timestamp).toISOString();
  const src = `[${SOURCE_LABELS[entry.source]}]`;
  const sev = SEVERITY_LABELS[entry.severity];
  return `${ts}  ${src}  ${sev}  ${entry.message}`;
}

function generateFilename(): string {
  const now = new Date();
  const y = now.getFullYear();
  const mo = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const h = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const s = String(now.getSeconds()).padStart(2, "0");
  return `scue-console-${y}${mo}${d}-${h}${mi}${s}.log`;
}

/** Format entries and trigger a browser file download. */
export function exportConsoleLog(entries: ConsoleEntry[]): void {
  const text = entries.map(formatEntryForExport).join("\n");
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = generateFilename();
  document.body.appendChild(a);
  a.click();

  // Cleanup
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
