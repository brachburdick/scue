/** M7 Event Detection types — mirrors Python MusicalEvent and DrumPattern. */

export interface MusicalEvent {
  type: EventType;
  timestamp: number; // seconds from track start
  duration: number | null; // null for instantaneous events
  intensity: number; // 0.0–1.0
  payload: Record<string, unknown>;
}

export type EventType =
  | "kick"
  | "snare"
  | "hihat"
  | "clap"
  | "riser"
  | "faller"
  | "stab";

export interface DrumPattern {
  bar_start: number;
  bar_end: number;
  kick: number[]; // 16 slots per bar (1=hit, 0=silent)
  snare: number[];
  clap: number[];
  hihat_type: "8ths" | "16ths" | "offbeat" | "roll" | "none";
  hihat_density: number; // 0.0–1.0
  hihat_open_ratio: number;
  confidence: number;
}

export interface TrackEventsResponse {
  fingerprint: string;
  events: MusicalEvent[];
  drum_patterns: DrumPattern[];
  total_events: number;
  total_patterns: number;
  event_types: EventType[];
}

/** Color mapping for event types on the timeline. */
export const EVENT_COLORS: Record<EventType, string> = {
  kick: "#ef4444",    // red
  snare: "#f97316",   // orange
  clap: "#eab308",    // yellow
  hihat: "#84cc16",   // lime
  riser: "#06b6d4",   // cyan
  faller: "#8b5cf6",  // violet
  stab: "#ec4899",    // pink
};

/** Section background colors (muted, for context bands). */
export const SECTION_COLORS: Record<string, string> = {
  intro: "rgba(148, 163, 184, 0.15)",
  verse: "rgba(96, 165, 250, 0.15)",
  build: "rgba(251, 191, 36, 0.15)",
  drop: "rgba(239, 68, 68, 0.15)",
  breakdown: "rgba(167, 139, 250, 0.15)",
  outro: "rgba(148, 163, 184, 0.15)",
};
