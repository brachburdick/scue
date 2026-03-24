/**
 * AnnotationPage — ground truth annotation tool for M7 event detection tuning.
 *
 * Route: /dev/annotate
 * Select a track, place events on the waveform, save as ground truth,
 * compare against detector output, and score with the eval harness.
 */

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrackPicker } from "../components/analysis/TrackPicker.tsx";
import { AnnotationTimeline } from "../components/annotations/AnnotationTimeline.tsx";
import { AnnotationToolbar } from "../components/annotations/AnnotationToolbar.tsx";
import { AnnotationList } from "../components/annotations/AnnotationList.tsx";
import { ScorePanel } from "../components/annotations/ScorePanel.tsx";
import {
  useGroundTruth,
  useSaveGroundTruth,
  useScoreGroundTruth,
} from "../api/groundTruth.ts";
import type { EventType, MusicalEvent, TrackEventsResponse } from "../types/events.ts";
import { useActiveEvents } from "../hooks/useActiveEvents.ts";
import { LiveEventDisplay } from "../components/shared/LiveEventDisplay.tsx";

const ALL_EVENT_TYPES: EventType[] = ["kick", "snare", "clap", "hihat", "riser", "faller", "stab"];
import type {
  GroundTruthEvent,
  SnapResolution,
  PlacementMode,
  ScoreResponse,
} from "../types/groundTruth.ts";

const API_BASE = "/api/tracks";

// --- Undo/Redo state ---

interface AnnotationState {
  events: GroundTruthEvent[];
}

function useAnnotationHistory(initial: GroundTruthEvent[]) {
  const [state, setState] = useState<AnnotationState>({ events: initial });
  const undoStack = useRef<AnnotationState[]>([]);
  const redoStack = useRef<AnnotationState[]>([]);
  const [, forceRender] = useState(0);

  const setEvents = useCallback((fn: (prev: GroundTruthEvent[]) => GroundTruthEvent[]) => {
    setState((prev) => {
      undoStack.current.push(prev);
      redoStack.current = [];
      forceRender((n) => n + 1);
      return { events: fn(prev.events) };
    });
  }, []);

  const reset = useCallback((events: GroundTruthEvent[]) => {
    setState({ events });
    undoStack.current = [];
    redoStack.current = [];
    forceRender((n) => n + 1);
  }, []);

  const undo = useCallback(() => {
    const prev = undoStack.current.pop();
    if (prev) {
      redoStack.current.push(state);
      setState(prev);
      forceRender((n) => n + 1);
    }
  }, [state]);

  const redo = useCallback(() => {
    const next = redoStack.current.pop();
    if (next) {
      undoStack.current.push(state);
      setState(next);
      forceRender((n) => n + 1);
    }
  }, [state]);

  return {
    events: state.events,
    setEvents,
    reset,
    undo,
    redo,
    canUndo: undoStack.current.length > 0,
    canRedo: redoStack.current.length > 0,
  };
}

// --- Page component ---

export function AnnotationPage() {
  const [fingerprint, setFingerprint] = useState<string | null>(null);
  const [activeType, setActiveType] = useState<EventType>("kick");
  const [placementMode, setPlacementMode] = useState<PlacementMode>("point");
  const [snapResolution, setSnapResolution] = useState<SnapResolution>("32nd");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [showDetectorOverlay, setShowDetectorOverlay] = useState(true);
  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(0);
  const [scoreData, setScoreData] = useState<ScoreResponse | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [visibleTypes, setVisibleTypes] = useState<Set<EventType>>(
    () => new Set(ALL_EVENT_TYPES),
  );

  // Audio playback
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<number | null>(null);
  const animFrameRef = useRef(0);

  // Annotation state with undo/redo
  const { events: annotations, setEvents, reset, undo, redo, canUndo, canRedo } =
    useAnnotationHistory([]);

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

  // Fetch detector events
  const { data: eventsData } = useQuery<TrackEventsResponse>({
    queryKey: ["track-events", fingerprint],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/${fingerprint}/events`);
      if (!res.ok) throw new Error("Events not found");
      return res.json();
    },
    enabled: !!fingerprint,
  });

  // Expand drum patterns for detector overlay
  const detectorEvents: MusicalEvent[] = useMemo(() => {
    if (!eventsData) return [];
    const tonal = eventsData.events ?? [];
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
            if (absSlot < pattern.kick.length && pattern.kick[absSlot])
              percussion.push({ type: "kick", timestamp: t, duration: null, intensity: 0.8, payload: {} });
            if (absSlot < pattern.snare.length && pattern.snare[absSlot])
              percussion.push({ type: "snare", timestamp: t, duration: null, intensity: 0.7, payload: {} });
            if (absSlot < pattern.clap.length && pattern.clap[absSlot])
              percussion.push({ type: "clap", timestamp: t, duration: null, intensity: 0.6, payload: {} });
          }
        }
      }
    }
    return [...tonal, ...percussion].sort((a, b) => a.timestamp - b.timestamp);
  }, [eventsData, analysis]);

  // Fetch existing ground truth
  const { data: gtData } = useGroundTruth(fingerprint);

  // Load ground truth when track changes, or pre-populate from detectors
  useEffect(() => {
    if (gtData?.updated_at != null && gtData.events.length > 0) {
      // Saved ground truth exists — use it
      reset(gtData.events);
      setIsDirty(false);
    } else if (gtData?.updated_at == null && detectorEvents.length > 0) {
      // No saved ground truth — pre-populate from detector predictions
      const prepopulated: GroundTruthEvent[] = detectorEvents.map((e) => ({
        type: e.type,
        timestamp: e.timestamp,
        duration: e.duration ?? undefined,
        source: "predicted" as const,
      }));
      reset(prepopulated);
      setIsDirty(true); // Mark dirty so user knows these are unsaved
    } else {
      reset([]);
      setIsDirty(false);
    }
    setScoreData(null);
    setSelectedIndex(null);
  }, [gtData, detectorEvents, reset]);

  // Set view range when analysis loads
  useEffect(() => {
    if (analysis?.duration) {
      setViewStart(0);
      setViewEnd(analysis.duration);
    }
  }, [analysis]);

  // Stop audio when track changes
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
      setCursorPosition(null);
    }
  }, [fingerprint]);

  // Save mutation
  const saveMutation = useSaveGroundTruth();
  const scoreMutation = useScoreGroundTruth();

  const handleSave = useCallback(() => {
    if (!fingerprint) return;
    saveMutation.mutate(
      { fingerprint, events: annotations },
      { onSuccess: () => setIsDirty(false) },
    );
  }, [fingerprint, annotations, saveMutation]);

  const handleScore = useCallback(() => {
    if (!fingerprint) return;
    // Save first if dirty
    const doScore = () => {
      scoreMutation.mutate(fingerprint, {
        onSuccess: (data) => setScoreData(data),
      });
    };
    if (isDirty) {
      saveMutation.mutate(
        { fingerprint, events: annotations },
        { onSuccess: () => { setIsDirty(false); doScore(); } },
      );
    } else {
      doScore();
    }
  }, [fingerprint, isDirty, annotations, saveMutation, scoreMutation]);

  // Event handlers
  const handlePlaceEvent = useCallback(
    (event: GroundTruthEvent) => {
      setEvents((prev) =>
        [...prev, { ...event, source: event.source ?? "manual" }].sort(
          (a, b) => a.timestamp - b.timestamp,
        ),
      );
      setIsDirty(true);
    },
    [setEvents],
  );

  const handleDeleteEvent = useCallback(
    (index: number) => {
      setEvents((prev) => prev.filter((_, i) => i !== index));
      setSelectedIndex(null);
      setIsDirty(true);
    },
    [setEvents],
  );

  const handleUndo = useCallback(() => {
    undo();
    setIsDirty(true);
    setSelectedIndex(null);
  }, [undo]);

  const handleRedo = useCallback(() => {
    redo();
    setIsDirty(true);
    setSelectedIndex(null);
  }, [redo]);

  const handleToggleTypeVisibility = useCallback((type: EventType) => {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleViewChange = useCallback((start: number, end: number) => {
    setViewStart(start);
    setViewEnd(end);
  }, []);

  // Audio playback
  const updateCursor = useCallback(() => {
    if (audioRef.current && !audioRef.current.paused) {
      setCursorPosition(audioRef.current.currentTime);
      animFrameRef.current = requestAnimationFrame(updateCursor);
    }
  }, []);

  const togglePlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      audio.play();
      setIsPlaying(true);
      animFrameRef.current = requestAnimationFrame(updateCursor);
    } else {
      audio.pause();
      setIsPlaying(false);
      cancelAnimationFrame(animFrameRef.current);
    }
  }, [updateCursor]);

  const handleTimeClick = useCallback((seconds: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = seconds;
      setCursorPosition(seconds);
    }
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Space: play/pause
      if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        togglePlayback();
        return;
      }
      // Delete/Backspace: remove selected
      if ((e.key === "Delete" || e.key === "Backspace") && selectedIndex !== null && e.target === document.body) {
        e.preventDefault();
        handleDeleteEvent(selectedIndex);
        return;
      }
      // Ctrl+Z: undo, Ctrl+Shift+Z: redo
      if (e.key === "z" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (e.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
        return;
      }
      // Ctrl+S: save
      if (e.key === "s" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [togglePlayback, selectedIndex, handleDeleteEvent, handleUndo, handleRedo, handleSave]);

  // Clean up animation frame
  useEffect(() => {
    return () => cancelAnimationFrame(animFrameRef.current);
  }, []);

  const duration = analysis?.duration ?? 0;
  const sections = analysis?.sections ?? [];
  const beats = (analysis?.beats ?? []) as number[];
  const downbeats = (analysis?.downbeats ?? []) as number[];

  // Shared playback context — drives LiveEventDisplay
  const visibleAnnotations = useMemo(
    () => annotations.filter((a) => visibleTypes.has(a.type)),
    [annotations, visibleTypes],
  );
  const activeState = useActiveEvents(
    cursorPosition,
    visibleAnnotations,
    sections,
    beats,
    downbeats,
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-white">Ground Truth Annotator</h1>
        <p className="text-sm text-slate-400 mt-1">
          Label events on the waveform to create ground truth for detector tuning.
        </p>
      </div>

      <TrackPicker selectedFingerprint={fingerprint} onSelect={setFingerprint} />

      {analysisLoading && (
        <div className="text-slate-400 text-sm animate-pulse">Loading track data...</div>
      )}

      {analysis && !analysisLoading && (
        <>
          {/* Track info + audio controls */}
          <div className="flex items-center gap-4 text-sm text-slate-400 bg-slate-800/50 rounded-lg px-4 py-2">
            <button
              onClick={togglePlayback}
              className="text-white hover:text-cyan-400 transition-colors text-lg"
              title="Space to play/pause"
            >
              {isPlaying ? "⏸" : "▶"}
            </button>
            <span className="text-white font-medium">{analysis.title}</span>
            <span>{analysis.bpm?.toFixed(1)} BPM</span>
            <span>{duration.toFixed(1)}s</span>
            <span>{sections.length} sections</span>
            <span className="text-cyan-400">{annotations.length} annotations</span>
            {cursorPosition != null && (
              <span className="font-mono text-slate-500">
                {Math.floor(cursorPosition / 60)}:{(cursorPosition % 60).toFixed(1).padStart(4, "0")}
              </span>
            )}
          </div>

          {/* Hidden audio element */}
          {fingerprint && (
            <audio
              ref={audioRef}
              src={`/api/audio/${fingerprint}`}
              preload="auto"
              onEnded={() => {
                setIsPlaying(false);
                cancelAnimationFrame(animFrameRef.current);
              }}
            />
          )}

          {/* Toolbar */}
          <AnnotationToolbar
            activeType={activeType}
            onTypeChange={setActiveType}
            placementMode={placementMode}
            onModeChange={setPlacementMode}
            snapResolution={snapResolution}
            onSnapChange={setSnapResolution}
            canUndo={canUndo}
            canRedo={canRedo}
            onUndo={handleUndo}
            onRedo={handleRedo}
            onSave={handleSave}
            isSaving={saveMutation.isPending}
            isDirty={isDirty}
            annotationCount={annotations.length}
            showDetectorOverlay={showDetectorOverlay}
            onToggleDetectorOverlay={() => setShowDetectorOverlay((v) => !v)}
            visibleTypes={visibleTypes}
            onToggleTypeVisibility={handleToggleTypeVisibility}
          />

          {/* Live event display */}
          <LiveEventDisplay state={activeState} layout="horizontal" />

          {/* Timeline */}
          <AnnotationTimeline
            sections={sections}
            waveform={analysis.waveform}
            duration={duration}
            annotations={annotations}
            selectedIndex={selectedIndex}
            detectorEvents={detectorEvents}
            showDetectorOverlay={showDetectorOverlay}
            cursorPosition={cursorPosition}
            activeType={activeType}
            placementMode={placementMode}
            snapResolution={snapResolution}
            beats={beats}
            downbeats={downbeats}
            viewStart={viewStart}
            viewEnd={viewEnd}
            visibleTypes={visibleTypes}
            onViewChange={handleViewChange}
            onPlaceEvent={handlePlaceEvent}
            onSelectEvent={setSelectedIndex}
            onTimeClick={handleTimeClick}
          />

          {/* List + Score panel */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <AnnotationList
              annotations={annotations}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
              onDelete={handleDeleteEvent}
              visibleTypes={visibleTypes}
            />
            <ScorePanel
              scoreData={scoreData}
              isScoring={scoreMutation.isPending}
              onScore={handleScore}
              hasAnnotations={annotations.length > 0}
              hasDetectedEvents={detectorEvents.length > 0}
            />
          </div>
        </>
      )}
    </div>
  );
}
