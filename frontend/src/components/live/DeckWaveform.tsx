import { useMemo, useState, useRef, useCallback, useEffect } from "react";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import type { RGBWaveform, Section } from "../../types";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";

const DEFAULT_WINDOW = 12;
const MIN_WINDOW = 1;
const MAX_WINDOW = 60;

export interface DeckWaveformProps {
  waveform: RGBWaveform;
  sections: Section[];
  duration: number;
  /** Current playback position in milliseconds, or null when stopped. */
  positionMs: number | null;
  /** BPM for smooth interpolation between WS updates */
  bpm?: number;
  /** Beatgrid data for overlay lines */
  beats?: number[];
  downbeats?: number[];
}

/**
 * Smooth position interpolation using requestAnimationFrame.
 * Bridges the gap between ~5Hz WS updates using wall-clock elapsed time.
 * Detects pause by checking if WS position stops advancing.
 */
function useSmoothedPosition(positionMs: number | null, bpm: number): number | null {
  const [smoothMs, setSmoothMs] = useState(positionMs);
  const lastWsMs = useRef(positionMs);
  const prevWsMs = useRef(positionMs);
  const lastWsTime = useRef(performance.now());
  const rafId = useRef<number>(0);
  const isAdvancing = useRef(false);

  // When WS delivers a new position, snap to it and detect if advancing
  useEffect(() => {
    // Detect if position is actually advancing (playing) vs static (paused)
    if (positionMs !== null && lastWsMs.current !== null) {
      const delta = Math.abs(positionMs - lastWsMs.current);
      // If position changed by more than 10ms, track is advancing
      isAdvancing.current = delta > 10;
    }
    prevWsMs.current = lastWsMs.current;
    lastWsMs.current = positionMs;
    lastWsTime.current = performance.now();
  }, [positionMs]);

  useEffect(() => {
    if (positionMs === null || bpm <= 0) {
      setSmoothMs(positionMs);
      return;
    }

    function tick() {
      const base = lastWsMs.current;
      if (base === null) {
        setSmoothMs(null);
        return;
      }
      if (!isAdvancing.current) {
        // Paused — just show the last known position, don't interpolate
        setSmoothMs(base);
        rafId.current = requestAnimationFrame(tick);
        return;
      }
      // Interpolate forward from last WS update using wall-clock elapsed time
      // Cap at 500ms ahead to avoid overshooting between WS gaps
      const elapsed = Math.min(500, performance.now() - lastWsTime.current);
      setSmoothMs(base + elapsed);
      rafId.current = requestAnimationFrame(tick);
    }

    rafId.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId.current);
  }, [positionMs, bpm]);

  return smoothMs;
}

export function DeckWaveform({
  waveform,
  sections,
  duration,
  positionMs,
  bpm = 0,
  beats,
  downbeats,
}: DeckWaveformProps) {
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);

  // Smooth position via rAF interpolation
  const smoothedMs = useSmoothedPosition(positionMs, bpm);
  const cursorSec = smoothedMs !== null ? smoothedMs / 1000 : null;

  // Zoom state: user can scroll-wheel to change window size
  const [windowSec, setWindowSec] = useState(DEFAULT_WINDOW);

  const { viewStart, viewEnd } = useMemo(() => {
    if (cursorSec === null) {
      return { viewStart: 0, viewEnd: Math.min(windowSec, duration) };
    }
    const half = windowSec / 2;
    const start = Math.max(0, cursorSec - half);
    const end = Math.min(duration, cursorSec + half);
    return { viewStart: start, viewEnd: end };
  }, [cursorSec, duration, windowSec]);

  // Handle zoom from WaveformCanvas scroll events
  const handleViewChange = useCallback(
    (newStart: number, newEnd: number) => {
      const newWindow = Math.max(MIN_WINDOW, Math.min(MAX_WINDOW, newEnd - newStart));
      setWindowSec(newWindow);
    },
    [],
  );

  const currentSectionIndex = useMemo(() => {
    if (cursorSec === null || !sections) return null;
    const idx = sections.findIndex(
      (s) => cursorSec >= s.start && cursorSec < s.end,
    );
    return idx >= 0 ? idx : null;
  }, [cursorSec, sections]);

  return (
    <WaveformCanvas
      waveform={waveform}
      sections={sections}
      duration={duration}
      beats={beats}
      downbeats={downbeats}
      viewStart={viewStart}
      viewEnd={viewEnd}
      onViewChange={handleViewChange}
      cursorPosition={cursorSec}
      highlightedSection={currentSectionIndex}
      selectedSection={null}
      renderParams={activeRenderParams}
    />
  );
}
