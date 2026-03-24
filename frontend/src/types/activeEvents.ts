/**
 * Active event state types for the shared playback context.
 *
 * useActiveEvents hook computes this from (currentTime, events, sections, beats)
 * and LiveEventDisplay renders it. Both are page-agnostic.
 */

import type { EventType } from "./events";
import type { Section } from "./track";
import type { AnnotationSource } from "./groundTruth";

/** An event that has recently fired (within the recency window). */
export interface FiredEvent {
  type: EventType;
  timestamp: number;
  duration?: number;
  /** Milliseconds since this event fired — drives fade-out animation. */
  age: number;
  /** Preserved from GroundTruthEvent source if present. */
  source?: AnnotationSource;
}

/** An upcoming event with countdown. */
export interface EventPreview {
  type: EventType;
  timestamp: number;
  /** Seconds until this event fires. */
  timeUntil: number;
}

/** Current position within the beatgrid phrase structure. */
export interface PhraseInfo {
  /** 0-indexed bar within current phrase (group of downbeats). */
  barInPhrase: number;
  /** Total bars in current phrase. */
  phraseLength: number;
  /** 0-indexed beat within current bar. */
  beatInBar: number;
  /** Beats per bar (typically 4). */
  beatsPerBar: number;
}

/** Complete active state at a given playback time. */
export interface ActiveEventState {
  currentTime: number;
  activeSections: Section[];
  recentEvents: FiredEvent[];
  upcomingEvents: EventPreview[];
  phrase: PhraseInfo | null;
}

/** Options for useActiveEvents hook. */
export interface ActiveEventOptions {
  /** Milliseconds to keep fired events visible (default 300). */
  recentWindow?: number;
  /** Number of upcoming events to preview (default 5). */
  previewCount?: number;
}
