/**
 * DetectorTuningPage — dev-only page for testing and tuning event detection.
 *
 * Route: /dev/detectors (not linked from main nav)
 * Loads a track's analysis, displays detected events on the waveform,
 * and provides controls for filtering, toggling, and comparing strategies.
 */

import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { EventTimeline } from "../components/detectors/EventTimeline.tsx";
import { EventControls } from "../components/detectors/EventControls.tsx";
import { EventStats } from "../components/detectors/EventStats.tsx";
import type { EventType, MusicalEvent, TrackEventsResponse } from "../types/events.ts";

const API_BASE = "/api/tracks";

const ALL_TYPES: EventType[] = ["kick", "snare", "clap", "hihat", "riser", "faller", "stab"];

export function DetectorTuningPage() {
  const [fingerprint, setFingerprint] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [visibleTypes, setVisibleTypes] = useState<Set<EventType>>(new Set(ALL_TYPES));
  const [minConfidence, setMinConfidence] = useState(0);

  // Fetch track analysis
  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ["track", fingerprint],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/${fingerprint}`);
      if (!res.ok) throw new Error("Track not found");
      return res.json();
    },
    enabled: !!fingerprint,
  });

  // Fetch events
  const { data: eventsData, isLoading: eventsLoading } = useQuery<TrackEventsResponse>({
    queryKey: ["track-events", fingerprint],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/${fingerprint}/events`);
      if (!res.ok) throw new Error("Events not found");
      return res.json();
    },
    enabled: !!fingerprint,
  });

  // Expand drum patterns into MusicalEvent[] for timeline display
  const allEvents: MusicalEvent[] = useMemo(() => {
    if (!eventsData) return [];

    const tonal = eventsData.events ?? [];

    // Expand patterns into kick/snare/clap events
    const percussion: MusicalEvent[] = [];
    if (analysis?.downbeats && analysis.beats && eventsData.drum_patterns) {
      const beats = analysis.beats as number[];
      const downbeats = analysis.downbeats as number[];
      const avgBeatDur =
        beats.length >= 2 ? (beats[beats.length - 1] - beats[0]) / (beats.length - 1) : 0.5;
      const sixteenthDur = avgBeatDur / 4;

      for (const pattern of eventsData.drum_patterns) {
        for (let bar = pattern.bar_start; bar < pattern.bar_end; bar++) {
          if (bar >= downbeats.length) break;
          const barTime = downbeats[bar];
          const localBar = bar - pattern.bar_start;
          const slotOffset = localBar * 16;

          for (let slot = 0; slot < 16; slot++) {
            const absSlot = slotOffset + slot;
            const t = barTime + slot * sixteenthDur;

            if (absSlot < pattern.kick.length && pattern.kick[absSlot]) {
              percussion.push({ type: "kick", timestamp: t, duration: null, intensity: 0.8, payload: {} });
            }
            if (absSlot < pattern.snare.length && pattern.snare[absSlot]) {
              percussion.push({ type: "snare", timestamp: t, duration: null, intensity: 0.7, payload: {} });
            }
            if (absSlot < pattern.clap.length && pattern.clap[absSlot]) {
              percussion.push({ type: "clap", timestamp: t, duration: null, intensity: 0.6, payload: {} });
            }
          }
        }
      }
    }

    return [...tonal, ...percussion].sort((a, b) => a.timestamp - b.timestamp);
  }, [eventsData, analysis]);

  const duration = analysis?.duration ?? 0;
  const sections = analysis?.sections ?? [];
  const totalBars = analysis?.downbeats?.length ?? 0;

  const handleToggleType = useCallback((type: EventType) => {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const handleLoad = () => {
    if (inputValue.trim()) {
      setFingerprint(inputValue.trim());
    }
  };

  const isLoading = analysisLoading || eventsLoading;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Detector Tuning</h1>
        <p className="text-sm text-slate-400 mt-1">
          Dev tool for testing and tuning event detection algorithms.
        </p>
      </div>

      {/* Track selector */}
      <div className="flex gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleLoad()}
          placeholder="Enter track fingerprint..."
          className="flex-1 bg-slate-800 text-white text-sm rounded-lg px-3 py-2 border border-slate-700 focus:border-cyan-500 focus:outline-none font-mono"
        />
        <button
          onClick={handleLoad}
          className="px-4 py-2 bg-cyan-600 text-white text-sm rounded-lg hover:bg-cyan-500 transition-colors"
        >
          Load
        </button>
      </div>

      {isLoading && (
        <div className="text-slate-400 text-sm animate-pulse">Loading track data...</div>
      )}

      {analysis && !isLoading && (
        <>
          {/* Track info bar */}
          <div className="flex items-center gap-4 text-sm text-slate-400 bg-slate-800/50 rounded-lg px-4 py-2">
            <span className="text-white font-medium">{analysis.title}</span>
            <span>{analysis.bpm?.toFixed(1)} BPM</span>
            <span>{duration.toFixed(1)}s</span>
            <span>{sections.length} sections</span>
            <span className="text-cyan-400">{allEvents.length} events</span>
          </div>

          {/* Timeline */}
          <EventTimeline
            events={allEvents}
            sections={sections}
            waveform={analysis.waveform}
            duration={duration}
            visibleTypes={visibleTypes}
            minConfidence={minConfidence}
            viewStart={0}
            viewEnd={duration}
          />

          {/* Controls + Stats */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-slate-800/50 rounded-lg p-4">
              <EventControls
                visibleTypes={visibleTypes}
                onToggleType={handleToggleType}
                minConfidence={minConfidence}
                onConfidenceChange={setMinConfidence}
              />
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4">
              <EventStats
                events={allEvents}
                totalBars={totalBars}
                duration={duration}
              />
            </div>
          </div>
        </>
      )}

      {!fingerprint && !isLoading && (
        <div className="text-center text-slate-600 py-12">
          Enter a track fingerprint to load its detected events.
        </div>
      )}
    </div>
  );
}
