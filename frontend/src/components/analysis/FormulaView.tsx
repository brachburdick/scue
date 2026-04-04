import { useState, useMemo, useCallback, useEffect } from "react";
import { useTrackAnalysis, useTrackEvents } from "../../api/tracks";
import { useSaveStrata } from "../../api/strata";
import { useWaveformView } from "../../hooks/useWaveformView";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import { ArrangementMap, LABEL_WIDTH } from "../strata/ArrangementMap";
import { PatternDetailPanel } from "../strata/PatternDetailPanel";
import { EventTypeToggles } from "../shared/EventTypeToggles";
import type { ArrangementFormula, StrataTier, Pattern, AtomicEvent } from "../../types/strata";
import type { EventType } from "../../types/events";

const TRANSITION_COLORS: Record<string, string> = {
  layer_enter: "text-green-400",
  layer_exit: "text-red-400",
  pattern_change: "text-yellow-400",
  fill: "text-orange-400",
  energy_shift: "text-blue-400",
  breakdown: "text-purple-400",
  drop_impact: "text-red-300",
};

interface FormulaViewProps {
  formula: ArrangementFormula;
  fingerprint: string;
  tier: StrataTier;
  editMode: boolean;
  onExitEdit: () => void;
  /** Real-time playback cursor position in seconds (live tier only). */
  playbackCursorTime?: number | null;
  /** Compare transitions to overlay on ArrangementMap (Lab mode). */
  compareTransitions?: import("../../types/strata").ArrangementTransition[];
}

export function FormulaView({ formula, fingerprint, tier, editMode, onExitEdit, playbackCursorTime, compareTransitions }: FormulaViewProps) {
  const { data: analysis } = useTrackAnalysis(fingerprint);
  const { data: trackEvents } = useTrackEvents(fingerprint);
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);
  const saveMutation = useSaveStrata(fingerprint, tier);

  const duration = analysis?.duration ?? formula.sections[formula.sections.length - 1]?.section_end ?? 0;
  const { viewStart, viewEnd, setView, zoomToSection } = useWaveformView(duration);

  const [selectedPatternId, setSelectedPatternId] = useState<string | null>(null);
  const [hoveredPatternId, setHoveredPatternId] = useState<string | null>(null);
  const [visibleEventTypes, setVisibleEventTypes] = useState<Set<string>>(new Set());
  const [showStemWaveforms, setShowStemWaveforms] = useState(true);
  const [showPatternBlocks, setShowPatternBlocks] = useState(true);

  const toggleEventType = useCallback((type: EventType) => {
    setVisibleEventTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  // --- Draft state for edit mode ---
  const [draft, setDraft] = useState<ArrangementFormula | null>(null);

  // Enter/exit edit mode -> snapshot or clear draft
  useEffect(() => {
    if (editMode) {
      setDraft(JSON.parse(JSON.stringify(formula)));
    } else {
      setDraft(null);
    }
  }, [editMode]); // eslint-disable-line react-hooks/exhaustive-deps

  /** The formula to display -- draft when editing, original otherwise. */
  const displayFormula = editMode && draft ? draft : formula;

  // Collect events for overlay: prefer per-stem strata events, fall back to M7 track-level events
  const allStemEvents: AtomicEvent[] = useMemo(() => {
    const strataEvents = displayFormula.stems.flatMap((s) => s.events);
    if (strataEvents.length > 0) return strataEvents;
    // Fall back to M7 track-level events (convert MusicalEvent -> AtomicEvent shape)
    if (trackEvents?.events?.length) {
      return trackEvents.events.map((e) => ({
        type: e.type,
        timestamp: e.timestamp,
        duration: e.duration,
        intensity: e.intensity,
        stem: null,
        pitch: null,
        beat_position: null,
        bar_index: null,
        confidence: e.intensity,
        source: "m7",
        payload: e.payload ?? {},
      }));
    }
    return [];
  }, [displayFormula.stems, trackEvents]);

  const isDirty = editMode && draft !== null && JSON.stringify(draft) !== JSON.stringify(formula);

  const handleSave = () => {
    if (!draft) return;
    saveMutation.mutate(
      { formula: draft as unknown as Record<string, unknown> },
      {
        onSuccess: () => {
          setDraft(null);
          onExitEdit();
        },
      },
    );
  };

  const handleDiscard = () => {
    setDraft(null);
    onExitEdit();
  };

  /** Update a pattern's name in the draft. */
  const updatePatternName = useCallback((patternId: string, newName: string) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        patterns: prev.patterns.map((p) =>
          p.id === patternId ? { ...p, name: newName } : p,
        ),
        stems: prev.stems.map((s) => ({
          ...s,
          patterns: s.patterns.map((p) =>
            p.id === patternId ? { ...p, name: newName } : p,
          ),
        })),
      };
    });
  }, []);

  /** Update a pattern's tags in the draft. */
  const updatePatternTags = useCallback((patternId: string, newTags: string[]) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        patterns: prev.patterns.map((p) =>
          p.id === patternId ? { ...p, tags: newTags } : p,
        ),
      };
    });
  }, []);

  const selectedPattern = useMemo(
    () => displayFormula.patterns.find((p) => p.id === selectedPatternId) ?? null,
    [displayFormula.patterns, selectedPatternId],
  );

  const selectAndZoomPattern = useCallback((pattern: Pattern) => {
    setSelectedPatternId(pattern.id);
    if (pattern.instances.length > 0) {
      const first = pattern.instances[0];
      zoomToSection(first.start, first.end, 0.3);
    }
  }, [zoomToSection]);

  const scrollToTime = useCallback((timestamp: number) => {
    const viewDuration = viewEnd - viewStart;
    const halfView = viewDuration / 2;
    let newStart = timestamp - halfView;
    let newEnd = timestamp + halfView;
    if (newStart < 0) { newEnd -= newStart; newStart = 0; }
    if (newEnd > duration) { newStart -= newEnd - duration; newEnd = duration; }
    setView(Math.max(0, newStart), Math.min(duration, newEnd));
  }, [viewStart, viewEnd, duration, setView]);

  // Convert strata sections to Section[] for WaveformCanvas
  const waveformSections = useMemo(
    () => displayFormula.sections.map((s) => ({
      label: s.section_label as import("../../types/track").SectionLabel,
      start: s.section_start,
      end: s.section_end,
      confidence: 1,
      bar_count: 0,
      expected_bar_count: 0,
      irregular_phrase: false,
      fakeout: false,
      original_label: s.section_label,
      source: "analysis" as const,
    })),
    [displayFormula.sections],
  );

  return (
    <div className="flex flex-col gap-4">
      {/* Edit mode toolbar */}
      {editMode && (
        <div className="flex items-center gap-3 px-4 py-2 bg-blue-950 border border-blue-800 rounded text-sm">
          <span className="text-blue-300">Edit Mode</span>
          {isDirty && (
            <span className="text-yellow-400 text-xs">Unsaved changes</span>
          )}
          {saveMutation.isError && (
            <span className="text-red-400 text-xs">Save failed: {saveMutation.error.message}</span>
          )}
          <div className="ml-auto flex gap-2">
            <button
              onClick={handleDiscard}
              className="px-3 py-1 text-xs rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
            >
              Discard
            </button>
            <button
              onClick={handleSave}
              disabled={!isDirty || saveMutation.isPending}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                isDirty && !saveMutation.isPending
                  ? "bg-blue-600 text-white hover:bg-blue-500"
                  : "bg-gray-800 text-gray-600 cursor-not-allowed"
              }`}
            >
              {saveMutation.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      )}

      {/* Summary bar */}
      <div className="flex items-center gap-4 px-4 py-2 bg-gray-950 rounded border border-gray-800 text-sm">
        <span className="text-gray-400">
          Tier: <span className="text-white">{displayFormula.pipeline_tier}</span>
        </span>
        <span className="text-gray-400">
          Layers: <span className="text-white">{displayFormula.total_layers}</span>
        </span>
        <span className="text-gray-400">
          Patterns: <span className="text-white">{displayFormula.total_patterns}</span>
        </span>
        <span className="text-gray-400">
          Transitions: <span className="text-white">{displayFormula.transitions.length}</span>
        </span>
        <span className="text-gray-400">
          Complexity: <span className="text-white">{displayFormula.arrangement_complexity.toFixed(2)}</span>
        </span>
        <span className="ml-auto text-gray-600 text-xs">
          {displayFormula.compute_time_seconds.toFixed(1)}s
        </span>
      </div>

      {/* Toolbar: event toggles + stem waveform toggle */}
      <div className="flex items-center gap-4 flex-wrap">
        {allStemEvents.length > 0 && (
          <EventTypeToggles
            visibleTypes={visibleEventTypes}
            onToggle={toggleEventType}
            compact
          />
        )}
        {displayFormula.stems.some((s) => s.waveform) && (
          <button
            onClick={() => setShowStemWaveforms((v) => !v)}
            className={`px-2 py-0.5 text-xs rounded border transition-colors ${
              showStemWaveforms
                ? "border-teal-500 text-teal-400"
                : "border-gray-700 text-gray-500 hover:text-gray-400"
            }`}
          >
            Stem Waveforms
          </button>
        )}
        <button
          onClick={() => setShowPatternBlocks((v) => !v)}
          className={`px-2 py-0.5 text-xs rounded border transition-colors ${
            showPatternBlocks
              ? "border-orange-500 text-orange-400"
              : "border-gray-700 text-gray-500 hover:text-gray-400"
          }`}
        >
          Pattern Blocks
        </button>
      </div>

      {/* Waveform + Section bands + Beatgrid */}
      {analysis?.waveform ? (
        <WaveformCanvas
          waveform={analysis.waveform}
          sections={waveformSections}
          energyCurve={analysis.features.energy_curve}
          duration={duration}
          beats={analysis.beats}
          downbeats={analysis.downbeats}
          viewStart={viewStart}
          viewEnd={viewEnd}
          onViewChange={setView}
          height={100}
          renderParams={activeRenderParams}
          leftPadding={LABEL_WIDTH}
        />
      ) : (
        <div className="h-24 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-600 text-xs">
            Waveform data loading{analysis === undefined ? "..." : " unavailable"}
          </p>
        </div>
      )}

      {/* Arrangement Map -- swim-lane view (synced zoom/scroll) */}
      <ArrangementMap
        formula={displayFormula}
        duration={duration}
        viewStart={viewStart}
        viewEnd={viewEnd}
        onViewChange={setView}
        selectedPatternId={selectedPatternId}
        hoveredPatternId={hoveredPatternId}
        onPatternSelect={setSelectedPatternId}
        onPatternHover={setHoveredPatternId}
        visibleEventTypes={visibleEventTypes}
        showStemWaveforms={showStemWaveforms}
        showPatternBlocks={showPatternBlocks}
        externalEvents={allStemEvents}
        playbackCursorTime={playbackCursorTime ?? undefined}
        compareTransitions={compareTransitions}
      />

      {/* Pattern Detail Panel (shown when a pattern is selected) */}
      {selectedPattern && (
        <PatternDetailPanel pattern={selectedPattern} />
      )}

      {/* Energy narrative */}
      {displayFormula.energy_narrative && (
        <div className="px-4 py-2 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Energy Narrative
          </span>
          <p className="text-sm text-gray-300 mt-1">
            {displayFormula.energy_narrative}
          </p>
        </div>
      )}

      {/* Two-column: Patterns + Transitions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Patterns */}
        <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Patterns ({displayFormula.patterns.length})
          </span>
          {displayFormula.patterns.length > 0 ? (
            <div className="mt-2 flex flex-col gap-2">
              {displayFormula.patterns.map((p) => (
                <div
                  key={p.id}
                  className={`flex flex-col gap-0.5 cursor-pointer rounded px-2 py-1 -mx-2 transition-colors ${
                    p.id === selectedPatternId
                      ? "bg-gray-800"
                      : p.id === hoveredPatternId
                        ? "bg-gray-850 bg-gray-800/50"
                        : "hover:bg-gray-900"
                  }`}
                  onClick={() => {
                    if (p.id === selectedPatternId) {
                      setSelectedPatternId(null);
                    } else {
                      selectAndZoomPattern(p);
                    }
                  }}
                  onMouseEnter={() => setHoveredPatternId(p.id)}
                  onMouseLeave={() => setHoveredPatternId(null)}
                >
                  <div className="flex items-center gap-2">
                    {editMode ? (
                      <input
                        type="text"
                        value={p.name}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => updatePatternName(p.id, e.target.value)}
                        className="text-sm text-gray-200 font-mono bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 w-40 focus:border-blue-500 focus:outline-none"
                      />
                    ) : (
                      <span className="text-sm text-gray-200 font-mono">{p.name}</span>
                    )}
                    {p.stem && (
                      <span className="text-xs px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded">
                        {p.stem}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{p.instances.length} instance{p.instances.length !== 1 ? "s" : ""}</span>
                    {editMode ? (
                      <input
                        type="text"
                        value={p.tags.join(", ")}
                        placeholder="tags (comma-separated)"
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => updatePatternTags(p.id, e.target.value.split(",").map((t) => t.trim()).filter(Boolean))}
                        className="text-xs text-gray-400 bg-gray-900 border border-gray-700 rounded px-1 py-0.5 w-32 focus:border-blue-500 focus:outline-none"
                      />
                    ) : (
                      <>
                        {p.tags.length > 0 && (
                          <span>{p.tags.join(", ")}</span>
                        )}
                      </>
                    )}
                    {p.template.signature && (
                      <span className="font-mono text-gray-600">{p.template.signature.slice(0, 8)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-600">No patterns detected.</p>
          )}
        </div>

        {/* Transitions */}
        <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Transitions ({displayFormula.transitions.length})
          </span>
          {displayFormula.transitions.length > 0 ? (
            <div className="mt-2 flex flex-col gap-1.5">
              {displayFormula.transitions.map((t, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-sm cursor-pointer rounded px-1 -mx-1 hover:bg-gray-900 transition-colors"
                  onClick={() => scrollToTime(t.timestamp)}
                >
                  <span className="text-gray-600 font-mono text-xs w-12 text-right">
                    {t.timestamp.toFixed(1)}s
                  </span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${TRANSITION_COLORS[t.type] ?? "text-gray-400"}`}>
                    {t.type.replace("_", " ")}
                  </span>
                  <span className="text-gray-400 text-xs truncate">
                    {t.description}
                  </span>
                  {t.energy_delta !== 0 && (
                    <span className={`text-xs ${t.energy_delta > 0 ? "text-green-500" : "text-red-500"}`}>
                      {t.energy_delta > 0 ? "+" : ""}{(t.energy_delta * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-600">No transitions detected.</p>
          )}
        </div>
      </div>

      {/* Sections */}
      {displayFormula.sections.length > 0 && (
        <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Section Arrangement ({displayFormula.sections.length})
          </span>
          <div className="mt-2 flex flex-col gap-1">
            {displayFormula.sections.map((s, i) => (
              <div
                key={i}
                className="flex items-center gap-3 text-sm py-1 border-b border-gray-900 last:border-0 cursor-pointer hover:bg-gray-900/50 transition-colors"
                onClick={() => zoomToSection(s.section_start, s.section_end)}
              >
                <span className="text-gray-200 w-24">{s.section_label}</span>
                <span className="text-gray-500 text-xs font-mono">
                  {s.section_start.toFixed(1)}s&ndash;{s.section_end.toFixed(1)}s
                </span>
                <span className="text-gray-500 text-xs">
                  {s.layer_count} layer{s.layer_count !== 1 ? "s" : ""}
                </span>
                <span className="text-gray-500 text-xs">
                  {s.active_patterns.length} pattern{s.active_patterns.length !== 1 ? "s" : ""}
                </span>
                <span className={`text-xs ${
                  s.energy_trend === "rising" ? "text-green-400" :
                  s.energy_trend === "falling" ? "text-red-400" :
                  s.energy_trend === "peak" ? "text-yellow-400" :
                  s.energy_trend === "valley" ? "text-blue-400" :
                  "text-gray-500"
                }`}>
                  {s.energy_trend}
                </span>
                <div className="ml-auto w-16 bg-gray-800 rounded-full h-1.5">
                  <div
                    className="bg-blue-500 h-1.5 rounded-full"
                    style={{ width: `${Math.round(s.energy_level * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
