import { useState, useCallback } from "react";

interface WaveformView {
  viewStart: number;
  viewEnd: number;
  setView: (start: number, end: number) => void;
  resetView: () => void;
  zoomToSection: (start: number, end: number, padding?: number) => void;
}

/**
 * Manages zoom/scroll state for a waveform view.
 * The WaveformCanvas component calls `setView` via its `onViewChange` callback.
 */
export function useWaveformView(duration: number): WaveformView {
  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(duration);

  // Update when duration changes (new track loaded)
  if (viewEnd > duration && duration > 0) {
    setViewEnd(duration);
    if (viewStart > duration) setViewStart(0);
  }

  const setView = useCallback(
    (start: number, end: number) => {
      setViewStart(Math.max(0, start));
      setViewEnd(Math.min(duration, end));
    },
    [duration],
  );

  const resetView = useCallback(() => {
    setViewStart(0);
    setViewEnd(duration);
  }, [duration]);

  const zoomToSection = useCallback(
    (start: number, end: number, padding = 0.1) => {
      const sectionDuration = end - start;
      const pad = sectionDuration * padding;
      const newStart = Math.max(0, start - pad);
      const newEnd = Math.min(duration, end + pad);
      setViewStart(newStart);
      setViewEnd(newEnd);
    },
    [duration],
  );

  return { viewStart, viewEnd, setView, resetView, zoomToSection };
}
