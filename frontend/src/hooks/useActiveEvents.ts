/**
 * useActiveEvents — shared playback context hook.
 *
 * Pure computation: given (currentTime, events, sections, beats, downbeats),
 * returns what sections are active, what events just fired, what's coming up,
 * and where we are in the phrase structure.
 *
 * No store dependencies. Each consumer provides its own cursor time.
 * Designed for 60fps cursor updates — uses binary search, not linear scan.
 */

import { useMemo, useRef } from "react";
import type { Section } from "../types/track";
import type { EventType } from "../types/events";
import type { AnnotationSource } from "../types/groundTruth";
import type {
  ActiveEventState,
  ActiveEventOptions,
  FiredEvent,
  EventPreview,
  PhraseInfo,
} from "../types/activeEvents";

/** Unified event shape for the hook — accepts both MusicalEvent and GroundTruthEvent. */
interface EventInput {
  type: EventType;
  timestamp: number;
  duration?: number | null;
  source?: AnnotationSource;
}

const DEFAULT_RECENT_WINDOW = 300; // ms
const DEFAULT_PREVIEW_COUNT = 5;

// --- Binary search utilities ---

/** Find the index of the first event with timestamp >= target. */
function lowerBound(events: EventInput[], target: number): number {
  let lo = 0;
  let hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (events[mid].timestamp < target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

/** Find the index of the first event with timestamp > target. */
function upperBound(events: EventInput[], target: number): number {
  let lo = 0;
  let hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (events[mid].timestamp <= target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

// --- Phrase computation ---

function computePhrase(
  currentTime: number,
  beats: number[],
  downbeats: number[],
): PhraseInfo | null {
  if (beats.length < 2 || downbeats.length < 2) return null;

  // Find current downbeat index (which bar are we in?)
  let barIdx = -1;
  for (let i = downbeats.length - 1; i >= 0; i--) {
    if (currentTime >= downbeats[i]) {
      barIdx = i;
      break;
    }
  }
  if (barIdx < 0) return null;

  // Phrase = group of 4 bars (standard EDM phrasing)
  const phraseLength = 4;
  const barInPhrase = barIdx % phraseLength;

  // Find beat within bar
  const barStart = downbeats[barIdx];
  const barEnd = barIdx + 1 < downbeats.length ? downbeats[barIdx + 1] : Infinity;

  let beatInBar = 0;
  for (let i = beats.length - 1; i >= 0; i--) {
    if (beats[i] >= barStart && beats[i] < barEnd && currentTime >= beats[i]) {
      // Count beats from bar start
      let count = 0;
      for (let j = i; j >= 0; j--) {
        if (beats[j] < barStart) break;
        count++;
      }
      beatInBar = count - 1;
      break;
    }
  }

  // Infer beats per bar from the data
  let beatsPerBar = 4;
  if (barIdx + 1 < downbeats.length) {
    let count = 0;
    for (const b of beats) {
      if (b >= barStart && b < barEnd) count++;
    }
    if (count > 0) beatsPerBar = count;
  }

  return { barInPhrase, phraseLength, beatInBar, beatsPerBar };
}

// --- Main hook ---

export function useActiveEvents(
  currentTime: number | null,
  events: EventInput[],
  sections: Section[],
  beats: number[],
  downbeats: number[],
  options?: ActiveEventOptions,
): ActiveEventState | null {
  const recentWindow = options?.recentWindow ?? DEFAULT_RECENT_WINDOW;
  const previewCount = options?.previewCount ?? DEFAULT_PREVIEW_COUNT;

  // Sort events once, stably (by timestamp)
  const sortedEvents = useMemo(() => {
    const copy = [...events];
    copy.sort((a, b) => a.timestamp - b.timestamp);
    return copy;
  }, [events]);

  // Cache previous result to avoid jitter
  const prevRef = useRef<ActiveEventState | null>(null);

  // Compute active state
  const result = useMemo((): ActiveEventState | null => {
    if (currentTime === null) return null;

    // Active sections: cursor inside [start, end)
    const activeSections = sections.filter(
      (s) => currentTime >= s.start && currentTime < s.end,
    );

    // Recent events: fired within [currentTime - windowSec, currentTime]
    const windowSec = recentWindow / 1000;
    const windowStart = currentTime - windowSec;

    const startIdx = lowerBound(sortedEvents, windowStart);
    const endIdx = upperBound(sortedEvents, currentTime);

    const recentEvents: FiredEvent[] = [];
    for (let i = endIdx - 1; i >= startIdx; i--) {
      const e = sortedEvents[i];
      if (e.timestamp < windowStart) break;
      recentEvents.push({
        type: e.type,
        timestamp: e.timestamp,
        duration: e.duration ?? undefined,
        age: (currentTime - e.timestamp) * 1000,
        source: e.source,
      });
    }

    // Upcoming events: next N after currentTime
    const upcomingStart = upperBound(sortedEvents, currentTime);
    const upcomingEvents: EventPreview[] = [];
    const limit = Math.min(upcomingStart + previewCount, sortedEvents.length);
    for (let i = upcomingStart; i < limit; i++) {
      const e = sortedEvents[i];
      upcomingEvents.push({
        type: e.type,
        timestamp: e.timestamp,
        timeUntil: e.timestamp - currentTime,
      });
    }

    // Phrase position
    const phrase = computePhrase(currentTime, beats, downbeats);

    return { currentTime, activeSections, recentEvents, upcomingEvents, phrase };
  }, [currentTime, sortedEvents, sections, beats, downbeats, recentWindow, previewCount]);

  // Update ref
  prevRef.current = result;

  return result;
}
