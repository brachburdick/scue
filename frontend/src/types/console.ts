/** Console panel types — log entries, sources, severities. */

export type ConsoleSource = "bridge" | "pioneer" | "system";
export type ConsoleSeverity = "info" | "warn" | "error";

export interface ConsoleEntry {
  id: string;
  timestamp: number;
  source: ConsoleSource;
  severity: ConsoleSeverity;
  message: string;
  verbose: boolean;
  raw?: unknown;
}
