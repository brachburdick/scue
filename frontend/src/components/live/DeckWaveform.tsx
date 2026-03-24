import { useMemo } from "react";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import type { RGBWaveform, Section } from "../../types";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";

const WINDOW_SECONDS = 12;

export interface DeckWaveformProps {
  waveform: RGBWaveform;
  sections: Section[];
  duration: number;
  /** Current playback position in milliseconds, or null when stopped. */
  positionMs: number | null;
  /** Beatgrid data for overlay lines */
  beats?: number[];
  downbeats?: number[];
}

export function DeckWaveform({ waveform, sections, duration, positionMs, beats, downbeats }: DeckWaveformProps) {
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);
  const cursorSec = positionMs !== null ? positionMs / 1000 : null;

  const { viewStart, viewEnd } = useMemo(() => {
    if (cursorSec === null) {
      return { viewStart: 0, viewEnd: Math.min(WINDOW_SECONDS, duration) };
    }
    const half = WINDOW_SECONDS / 2;
    const start = Math.max(0, cursorSec - half);
    const end = Math.min(duration, cursorSec + half);
    return { viewStart: start, viewEnd: end };
  }, [cursorSec, duration]);

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
      cursorPosition={cursorSec}
      highlightedSection={currentSectionIndex}
      selectedSection={null}
      renderParams={activeRenderParams}
    />
  );
}
