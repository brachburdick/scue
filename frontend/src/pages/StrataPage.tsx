import { useState, useMemo, useCallback, useEffect } from "react";
import { TrackPicker } from "../components/analysis/TrackPicker";
import { useStrataAllTiers, useAnalyzeStrata, useSaveStrata, useReanalyze, useTrackVersions } from "../api/strata";
import { useTrackAnalysis } from "../api/tracks";
import { useWaveformView } from "../hooks/useWaveformView";
import { useWaveformPresetStore } from "../stores/waveformPresetStore";
import { WaveformCanvas } from "../components/shared/WaveformCanvas";
import { ArrangementMap } from "../components/strata/ArrangementMap";
import { PatternDetailPanel } from "../components/strata/PatternDetailPanel";
import { ComparisonView } from "../components/strata/ComparisonView";
import type { AnalysisSource, ArrangementFormula, StrataTier, Pattern } from "../types/strata";

const SOURCE_LABELS: Record<AnalysisSource, string> = {
  analysis: "Original",
  pioneer_enriched: "Enriched",
  pioneer_reanalyzed: "Reanalyzed",
};

type PageMode = "view" | "edit" | "compare";

const TIER_LABELS: Record<StrataTier, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
};

const TIER_DESCRIPTIONS: Record<StrataTier, string> = {
  quick: "M7 heuristics + energy analysis (~3-7s)",
  standard: "Stem separation + per-stem analysis (~1-2 min)",
  deep: "Stem separation + ML models (~2-5 min)",
};

const TRANSITION_COLORS: Record<string, string> = {
  layer_enter: "text-green-400",
  layer_exit: "text-red-400",
  pattern_change: "text-yellow-400",
  fill: "text-orange-400",
  energy_shift: "text-blue-400",
  breakdown: "text-purple-400",
  drop_impact: "text-red-300",
};

export function StrataPage() {
  const [fingerprint, setFingerprint] = useState<string | null>(null);
  const [selectedTier, setSelectedTier] = useState<StrataTier>("quick");
  const [selectedSource, setSelectedSource] = useState<AnalysisSource>("analysis");
  const [pageMode, setPageMode] = useState<PageMode>("view");
  const [compareTier, setCompareTier] = useState<StrataTier>("standard");
  const [compareSource, _setCompareSource] = useState<AnalysisSource>("analysis");
  const { data, isLoading, refetch } = useStrataAllTiers(fingerprint);
  const analyzeMutation = useAnalyzeStrata(fingerprint);
  const reanalyzeMutation = useReanalyze(fingerprint);
  const { data: versionsData } = useTrackVersions(fingerprint);

  const availableTiers = data?.available_tiers ?? [];
  // Resolve formula from the nested tier→source structure
  const tierSources = data?.tiers?.[selectedTier];
  const formula: ArrangementFormula | null = tierSources?.[selectedSource] ?? (tierSources ? Object.values(tierSources)[0] ?? null : null);
  const hasAnyData = availableTiers.length > 0;

  // Available sources for the selected tier
  const availableSourcesForTier = tierSources ? Object.keys(tierSources) as AnalysisSource[] : [];
  // For comparison: collect all (tier, source) combos
  const compareTierSources = data?.tiers?.[compareTier];
  const compareFormula: ArrangementFormula | null = compareTierSources?.[compareSource] ?? (compareTierSources ? Object.values(compareTierSources)[0] ?? null : null);
  // Can compare if there are at least 2 distinct (tier, source) combos
  const totalCombos = Object.entries(data?.tiers ?? {}).reduce((acc, [, sources]) => acc + Object.keys(sources ?? {}).length, 0);
  const canCompare = totalCombos >= 2;

  const hasV2 = versionsData?.versions?.some((v) => v.source === "pioneer_enriched") ?? false;
  const hasV3 = versionsData?.versions?.some((v) => v.source === "pioneer_reanalyzed") ?? false;

  const handleAnalyze = () => {
    analyzeMutation.mutate(
      { tiers: ["quick"] },
      { onSuccess: () => refetch() },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Strata</h1>
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setPageMode("view")}
            className={pageMode === "view" ? "text-white" : "text-gray-500 hover:text-gray-300"}
          >
            View
          </button>
          <span className="text-gray-700">|</span>
          <button
            onClick={() => formula && setPageMode("edit")}
            disabled={!formula}
            className={pageMode === "edit"
              ? "text-white"
              : formula
                ? "text-gray-500 hover:text-gray-300"
                : "text-gray-700 cursor-not-allowed"
            }
          >
            Edit
          </button>
          <span className="text-gray-700">|</span>
          <button
            onClick={() => canCompare && setPageMode("compare")}
            disabled={!canCompare}
            title={canCompare ? "Compare two tiers side by side" : "Need 2+ tiers to compare"}
            className={pageMode === "compare"
              ? "text-white"
              : canCompare
                ? "text-gray-500 hover:text-gray-300"
                : "text-gray-700 cursor-not-allowed"
            }
          >
            Compare
          </button>
        </div>
      </div>

      {/* Track Picker */}
      <TrackPicker selectedFingerprint={fingerprint} onSelect={setFingerprint} />

      {fingerprint ? (
        <div className="flex flex-col gap-4">
          {/* Tier Selector + Analyze */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Tier:</span>
            {(["quick", "standard", "deep"] as StrataTier[]).map((tier) => {
              const isAvailable = availableTiers.includes(tier);
              const isSelected = tier === selectedTier;
              return (
                <button
                  key={tier}
                  onClick={() => isAvailable && setSelectedTier(tier)}
                  disabled={!isAvailable}
                  title={
                    isAvailable
                      ? TIER_DESCRIPTIONS[tier]
                      : `No ${tier} analysis available`
                  }
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    isSelected && isAvailable
                      ? "bg-blue-600 text-white"
                      : isAvailable
                        ? "bg-gray-800 text-gray-300 hover:bg-gray-700"
                        : "bg-gray-900 text-gray-600 cursor-not-allowed"
                  }`}
                >
                  {TIER_LABELS[tier]}
                </button>
              );
            })}

            {pageMode === "compare" && (
              <>
                <span className="text-gray-600 text-sm">vs</span>
                {(["quick", "standard", "deep"] as StrataTier[]).map((tier) => {
                  const isAvailable = availableTiers.includes(tier) && tier !== selectedTier;
                  const isSelected = tier === compareTier;
                  return (
                    <button
                      key={`cmp-${tier}`}
                      onClick={() => isAvailable && setCompareTier(tier)}
                      disabled={!isAvailable}
                      title={
                        tier === selectedTier
                          ? "Same as base tier"
                          : isAvailable
                            ? `Compare with ${tier}`
                            : `No ${tier} data`
                      }
                      className={`px-3 py-1 text-sm rounded transition-colors ${
                        isSelected && isAvailable
                          ? "bg-purple-600 text-white"
                          : isAvailable
                            ? "bg-gray-800 text-gray-300 hover:bg-gray-700"
                            : "bg-gray-900 text-gray-600 cursor-not-allowed"
                      }`}
                    >
                      {TIER_LABELS[tier]}
                    </button>
                  );
                })}
              </>
            )}

            {/* Source selector (shown when tier has multiple sources) */}
            {availableSourcesForTier.length > 1 && pageMode !== "compare" && (
              <>
                <span className="text-gray-600 ml-2">|</span>
                <span className="text-sm text-gray-400">Source:</span>
                {availableSourcesForTier.map((src) => (
                  <button
                    key={src}
                    onClick={() => setSelectedSource(src)}
                    className={`px-2 py-0.5 text-xs rounded transition-colors ${
                      src === selectedSource
                        ? "bg-teal-700 text-white"
                        : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                    }`}
                  >
                    {SOURCE_LABELS[src]}
                  </button>
                ))}
              </>
            )}

            <div className="ml-auto flex gap-2">
              <button
                onClick={handleAnalyze}
                disabled={analyzeMutation.isPending}
                className={`px-3 py-1.5 text-sm rounded transition-colors ${
                  analyzeMutation.isPending
                    ? "bg-blue-800 text-blue-300 cursor-wait"
                    : "bg-blue-600 text-white hover:bg-blue-500"
                }`}
              >
                {analyzeMutation.isPending ? "Analyzing..." : "Analyze Quick"}
              </button>
              {hasV2 && !hasV3 && (
                <button
                  onClick={() => reanalyzeMutation.mutate(undefined, { onSuccess: () => refetch() })}
                  disabled={reanalyzeMutation.isPending}
                  title="Re-run section & event detection with Pioneer beatgrid"
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    reanalyzeMutation.isPending
                      ? "bg-teal-800 text-teal-300 cursor-wait"
                      : "bg-teal-700 text-white hover:bg-teal-600"
                  }`}
                >
                  {reanalyzeMutation.isPending ? "Re-analyzing..." : "Re-analyze (Pioneer Grid)"}
                </button>
              )}
            </div>
          </div>

          {/* Error from analysis */}
          {analyzeMutation.isError && (
            <div className="px-4 py-2 bg-red-950 border border-red-800 rounded text-sm text-red-300">
              Analysis failed: {analyzeMutation.error.message}
            </div>
          )}

          {/* Content Area */}
          {isLoading ? (
            <div className="h-64 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
              <p className="text-gray-500 text-sm">Loading strata data...</p>
            </div>
          ) : !hasAnyData ? (
            <EmptyState onAnalyze={handleAnalyze} isAnalyzing={analyzeMutation.isPending} />
          ) : pageMode === "compare" && formula && compareFormula ? (
            <ComparisonView
              fingerprint={fingerprint}
              baseTier={selectedTier}
              compareTier={compareTier}
              baseFormula={formula}
              compareFormula={compareFormula}
            />
          ) : pageMode === "compare" && (!formula || !compareFormula) ? (
            <div className="h-48 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
              <p className="text-gray-500 text-sm">
                Select two available tiers to compare.
              </p>
            </div>
          ) : formula ? (
            <FormulaView
              formula={formula}
              fingerprint={fingerprint}
              tier={selectedTier}
              editMode={pageMode === "edit"}
              onExitEdit={() => setPageMode("view")}
            />
          ) : (
            <div className="h-48 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
              <p className="text-gray-500 text-sm">
                No {selectedTier} tier data. Select an available tier above.
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="h-40 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-500 text-sm">
            Select a track above to view arrangement analysis
          </p>
        </div>
      )}
    </div>
  );
}

function EmptyState({ onAnalyze, isAnalyzing }: { onAnalyze: () => void; isAnalyzing: boolean }) {
  return (
    <div className="h-64 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
      <p className="text-gray-500 text-sm">
        No strata analysis for this track yet.
      </p>
      <p className="text-gray-600 text-xs max-w-md text-center">
        The Strata engine decomposes tracks into layers, patterns, and
        transitions. Run quick analysis to generate arrangement data.
      </p>
      <button
        onClick={onAnalyze}
        disabled={isAnalyzing}
        className={`px-4 py-1.5 text-sm rounded transition-colors ${
          isAnalyzing
            ? "bg-blue-800 text-blue-300 cursor-wait"
            : "bg-blue-600 text-white hover:bg-blue-500"
        }`}
      >
        {isAnalyzing ? "Analyzing..." : "Run Quick Analysis"}
      </button>
    </div>
  );
}

interface FormulaViewProps {
  formula: ArrangementFormula;
  fingerprint: string;
  tier: StrataTier;
  editMode: boolean;
  onExitEdit: () => void;
}

function FormulaView({ formula, fingerprint, tier, editMode, onExitEdit }: FormulaViewProps) {
  const { data: analysis } = useTrackAnalysis(fingerprint);
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);
  const saveMutation = useSaveStrata(fingerprint, tier);

  const duration = analysis?.duration ?? formula.sections[formula.sections.length - 1]?.section_end ?? 0;
  const { viewStart, viewEnd, setView, zoomToSection } = useWaveformView(duration);

  const [selectedPatternId, setSelectedPatternId] = useState<string | null>(null);
  const [hoveredPatternId, setHoveredPatternId] = useState<string | null>(null);

  // --- Draft state for edit mode ---
  const [draft, setDraft] = useState<ArrangementFormula | null>(null);

  // Enter/exit edit mode → snapshot or clear draft
  useEffect(() => {
    if (editMode) {
      setDraft(JSON.parse(JSON.stringify(formula)));
    } else {
      setDraft(null);
    }
  }, [editMode]); // eslint-disable-line react-hooks/exhaustive-deps — intentionally only react to editMode toggle

  /** The formula to display — draft when editing, original otherwise. */
  const displayFormula = editMode && draft ? draft : formula;

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
      label: s.section_label as import("../types/track").SectionLabel,
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
        />
      ) : (
        <div className="h-24 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-600 text-xs">
            Waveform data loading{analysis === undefined ? "..." : " unavailable"}
          </p>
        </div>
      )}

      {/* Arrangement Map — swim-lane view (synced zoom/scroll) */}
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
                  {s.section_start.toFixed(1)}s–{s.section_end.toFixed(1)}s
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
