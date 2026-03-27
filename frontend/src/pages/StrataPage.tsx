import { useState, useMemo, useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { TrackPicker } from "../components/analysis/TrackPicker";
import {
  useStrataAllTiers,
  useAnalyzeStrata,
  useSaveStrata,
  useReanalyze,
  useTrackVersions,
  useAnalyzeStrataBatch,
  useLiveStrata,
} from "../api/strata";
import { useTrackAnalysis, useTrackEvents } from "../api/tracks";
import { apiFetch } from "../api/client";
import { useWaveformView } from "../hooks/useWaveformView";
import { useWaveformPresetStore } from "../stores/waveformPresetStore";
import { useBridgeStore } from "../stores/bridgeStore";
import { WaveformCanvas } from "../components/shared/WaveformCanvas";
import { ArrangementMap, LABEL_WIDTH } from "../components/strata/ArrangementMap";
import { PatternDetailPanel } from "../components/strata/PatternDetailPanel";
import { ComparisonView } from "../components/strata/ComparisonView";
import { StrataJobProgress, StrataBatchProgress } from "../components/strata/TierAnalysisStatus";
import type { AnalysisSource, ArrangementFormula, StrataTier, Pattern, AtomicEvent } from "../types/strata";
import type { EventType } from "../types/events";
import { EventTypeToggles } from "../components/shared/EventTypeToggles";

import { useStrataLiveStore } from "../stores/strataLiveStore";

const SOURCE_LABELS: Record<AnalysisSource, string> = {
  analysis: "Original",
  pioneer_enriched: "Enriched",
  pioneer_reanalyzed: "Reanalyzed",
  pioneer_live: "Live (Pioneer)",
};

type PageMode = "view" | "edit" | "compare" | "batch";

const TIER_LABELS: Record<StrataTier, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
  live: "Live",
  live_offline: "Live Offline",
};

const TIER_DESCRIPTIONS: Record<StrataTier, string> = {
  quick: "M7 heuristics + energy analysis (~3-7s)",
  standard: "Stem separation + per-stem analysis (~1-2 min)",
  deep: "Stem separation + ML models (~2-5 min)",
  live: "Pioneer hardware data (real-time, no audio needed)",
  live_offline: "Saved Pioneer data (no hardware or audio needed)",
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
  const queryClient = useQueryClient();
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

  // Job tracking for standard/deep analysis
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJobTier, setActiveJobTier] = useState<StrataTier | null>(null);

  // Batch analysis state
  const [selectedFingerprints, setSelectedFingerprints] = useState<Set<string>>(new Set());
  const [batchTiers, setBatchTiers] = useState<Set<StrataTier>>(new Set(["quick"]));
  const [batchId, setBatchId] = useState<string | null>(null);
  const batchMutation = useAnalyzeStrataBatch();

  // Bridge status for deep tier + live tier
  const bridgeStatus = useBridgeStore((s) => s.status);
  const devices = useBridgeStore((s) => s.devices);
  const players = useBridgeStore((s) => s.players);
  const hardwareConnected = bridgeStatus === "running" && Object.keys(devices).length > 0;

  // Live strata: merge REST polling + WS push
  const wsLiveFormulas = useStrataLiveStore((s) => s.formulas);
  const { data: restLiveData } = useLiveStrata(selectedTier === "live");

  // Merge: WS formulas override REST (more recent), REST fills in on page load
  const liveFormulas = useMemo(() => {
    const merged: Record<number, ArrangementFormula> = {};
    // REST data as base
    if (restLiveData?.players) {
      for (const [pn, f] of Object.entries(restLiveData.players)) {
        merged[Number(pn)] = f;
      }
    }
    // WS data overrides (more recent)
    for (const [pn, f] of Object.entries(wsLiveFormulas)) {
      merged[Number(pn)] = f;
    }
    return merged;
  }, [restLiveData, wsLiveFormulas]);

  const hasLiveData = Object.keys(liveFormulas).length > 0;

  // Find the first player with live strata (or the on-air one)
  const livePlayerNumber = useMemo(() => {
    const playerNums = Object.keys(liveFormulas).map(Number);
    if (playerNums.length === 0) return null;
    // Prefer on-air player
    const onAir = playerNums.find((pn) => players[String(pn)]?.is_on_air);
    return onAir ?? playerNums[0];
  }, [liveFormulas, players]);

  const liveFormula: ArrangementFormula | null = livePlayerNumber != null ? liveFormulas[livePlayerNumber] ?? null : null;

  // Get playback position for cursor (ms → seconds)
  const livePlaybackTime = useMemo(() => {
    if (livePlayerNumber == null) return null;
    const player = players[String(livePlayerNumber)];
    if (!player?.playback_position_ms) return null;
    return player.playback_position_ms / 1000;
  }, [livePlayerNumber, players]);

  const isLiveTier = selectedTier === "live";

  const availableTiers = data?.available_tiers ?? [];
  // For live tier: prefer real-time data, fall back to persisted data from useStrataAllTiers
  const persistedLiveSources = data?.tiers?.["live"];
  const persistedLiveFormula: ArrangementFormula | null = persistedLiveSources
    ? persistedLiveSources[selectedSource] ?? Object.values(persistedLiveSources)[0] ?? null
    : null;
  const tierSources = !isLiveTier ? data?.tiers?.[selectedTier] : undefined;
  const formula: ArrangementFormula | null = isLiveTier
    ? liveFormula ?? persistedLiveFormula
    : tierSources?.[selectedSource] ?? (tierSources ? Object.values(tierSources)[0] ?? null : null);
  const hasAnyData = availableTiers.length > 0 || hasLiveData;

  const activeTierSources = isLiveTier ? persistedLiveSources : tierSources;
  const availableSourcesForTier = activeTierSources ? Object.keys(activeTierSources) as AnalysisSource[] : [];
  const compareTierSources = data?.tiers?.[compareTier];
  const compareFormula: ArrangementFormula | null = compareTierSources?.[compareSource] ?? (compareTierSources ? Object.values(compareTierSources)[0] ?? null : null);
  const totalCombos = Object.entries(data?.tiers ?? {}).reduce((acc, [, sources]) => acc + Object.keys(sources ?? {}).length, 0);
  const canCompare = totalCombos >= 2;

  const hasV2 = versionsData?.versions?.some((v) => v.source === "pioneer_enriched") ?? false;
  const hasV3 = versionsData?.versions?.some((v) => v.source === "pioneer_reanalyzed") ?? false;

  const tierHasData = (tier: StrataTier) =>
    tier === "live" ? hasLiveData || availableTiers.includes("live") : availableTiers.includes(tier);

  const handleAnalyze = useCallback((tier: StrataTier) => {
    analyzeMutation.mutate(
      { tiers: [tier] },
      {
        onSuccess: (result) => {
          if (result.job_id) {
            // Standard/deep: track via job polling
            setActiveJobId(result.job_id);
            setActiveJobTier(tier);
          } else {
            // Quick: already complete
            refetch();
          }
        },
      },
    );
  }, [analyzeMutation, refetch]);

  const handleJobComplete = useCallback(() => {
    setActiveJobId(null);
    setActiveJobTier(null);
    refetch();
  }, [refetch]);

  const handleJobCancel = useCallback(() => {
    if (activeJobId) {
      apiFetch(`/strata/jobs/${activeJobId}/cancel`, { method: "POST" }).catch(() => {});
    }
    setActiveJobId(null);
    setActiveJobTier(null);
  }, [activeJobId]);

  const handleBatchAnalyze = useCallback(() => {
    if (selectedFingerprints.size === 0 || batchTiers.size === 0) return;
    batchMutation.mutate(
      { fingerprints: [...selectedFingerprints], tiers: [...batchTiers] },
      {
        onSuccess: (result) => {
          setBatchId(result.batch_id);
        },
      },
    );
  }, [selectedFingerprints, batchTiers, batchMutation]);

  const handleBatchComplete = useCallback(() => {
    setBatchId(null);
    // Invalidate strata data for all selected fingerprints
    for (const fp of selectedFingerprints) {
      queryClient.invalidateQueries({ queryKey: ["strata", fp] });
    }
    if (fingerprint) refetch();
  }, [selectedFingerprints, fingerprint, refetch, queryClient]);

  const handleTierClick = useCallback((tier: StrataTier) => {
    // Always switch view to this tier
    setSelectedTier(tier);
    // If in batch mode, don't trigger analysis
    if (pageMode === "batch") return;
  }, [pageMode]);

  /** Get the analyze button label for a tier */
  const getAnalyzeLabel = (tier: StrataTier): string => {
    if (analyzeMutation.isPending && activeJobTier === tier) return "Analyzing...";
    if (tierHasData(tier)) return `Re-run ${TIER_LABELS[tier]} (overwrites)`;
    return `Analyze ${TIER_LABELS[tier]}`;
  };

  /** Get tooltip for a tier button */
  const getTierTooltip = (tier: StrataTier): string => {
    if (tier === "deep" && !hardwareConnected) return "Requires Pioneer hardware connection";
    if (tierHasData(tier)) return TIER_DESCRIPTIONS[tier];
    return `Click to view \u2014 ${TIER_DESCRIPTIONS[tier]}`;
  };

  /** Can we trigger analysis for this tier? */
  const canAnalyzeTier = (tier: StrataTier): boolean => {
    if (analyzeMutation.isPending || activeJobId !== null) return false;
    if (tier === "deep" && !hardwareConnected) return false;
    return true;
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Strata</h1>
        <div className="flex items-center gap-2 text-xs">
          {(["view", "edit", "compare", "batch"] as PageMode[]).map((mode) => {
            const disabled =
              (mode === "edit" && !formula) ||
              (mode === "compare" && !canCompare);
            const titles: Record<PageMode, string> = {
              view: "View arrangement",
              edit: formula ? "Edit arrangement" : "Select a tier with data first",
              compare: canCompare ? "Compare two tiers" : "Need 2+ tiers to compare",
              batch: "Batch analyze multiple tracks",
            };
            return (
              <span key={mode}>
                {mode !== "view" && <span className="text-gray-700 mr-2">|</span>}
                <button
                  onClick={() => !disabled && setPageMode(mode)}
                  disabled={disabled}
                  title={titles[mode]}
                  className={pageMode === mode
                    ? "text-white"
                    : disabled
                      ? "text-gray-700 cursor-not-allowed"
                      : "text-gray-500 hover:text-gray-300"
                  }
                >
                  {mode.charAt(0).toUpperCase() + mode.slice(1)}
                </button>
              </span>
            );
          })}
        </div>
      </div>

      {/* Track Picker — single select normally, multi in batch mode */}
      {pageMode === "batch" ? (
        <TrackPicker
          mode="multi"
          selectedFingerprints={selectedFingerprints}
          onSelectionChange={setSelectedFingerprints}
        />
      ) : (
        <TrackPicker selectedFingerprint={fingerprint} onSelect={setFingerprint} />
      )}

      {/* Batch Mode UI */}
      {pageMode === "batch" && (
        <BatchPanel
          selectedCount={selectedFingerprints.size}
          batchTiers={batchTiers}
          onToggleTier={(tier) => {
            const next = new Set(batchTiers);
            if (next.has(tier)) next.delete(tier);
            else next.add(tier);
            setBatchTiers(next);
          }}
          onAnalyze={handleBatchAnalyze}
          isAnalyzing={batchMutation.isPending}
          batchId={batchId}
          onBatchComplete={handleBatchComplete}
          hardwareConnected={hardwareConnected}
        />
      )}

      {/* Single-track view (non-batch mode) */}
      {pageMode !== "batch" && (fingerprint || isLiveTier) ? (
        <div className="flex flex-col gap-4">
          {/* Tier Selector */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Tier:</span>
            {(["quick", "standard", "deep", "live", "live_offline"] as StrataTier[]).map((tier) => {
              const isAvailable = tierHasData(tier);
              const isSelected = tier === selectedTier;
              const isDeep = tier === "deep";
              const isLive = tier === "live";
              const isLiveOffline = tier === "live_offline";
              const disabled = (isDeep && !hardwareConnected && !isAvailable);

              return (
                <button
                  key={tier}
                  onClick={() => handleTierClick(tier)}
                  disabled={disabled}
                  title={getTierTooltip(tier)}
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    isSelected
                      ? isAvailable
                        ? isLive ? "bg-green-600 text-white" : isLiveOffline ? "bg-amber-600 text-white" : "bg-blue-600 text-white"
                        : isLive ? "bg-green-900 text-green-300 border border-green-700" : isLiveOffline ? "bg-amber-900 text-amber-300 border border-amber-700" : "bg-blue-900 text-blue-300 border border-blue-700"
                      : isAvailable
                        ? isLive ? "bg-gray-800 text-green-400 hover:bg-gray-700" : isLiveOffline ? "bg-gray-800 text-amber-400 hover:bg-gray-700" : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                        : disabled
                          ? "bg-gray-900 text-gray-600 cursor-not-allowed"
                          : "bg-gray-900 text-gray-500 hover:bg-gray-800 hover:text-gray-400 border border-dashed border-gray-700"
                  }`}
                >
                  {isLive && isAvailable && <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 animate-pulse" />}
                  {TIER_LABELS[tier]}
                </button>
              );
            })}

            {pageMode === "compare" && (
              <>
                <span className="text-gray-600 text-sm">vs</span>
                {(["quick", "standard", "deep"] as StrataTier[]).map((tier) => {
                  const isAvailable = tierHasData(tier) && tier !== selectedTier;
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

            {/* Source selector */}
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

            {/* Right-aligned actions */}
            <div className="ml-auto flex gap-2">
              {/* Re-run / Analyze button for current tier (not for live) */}
              {selectedTier !== "deep" && selectedTier !== "live" && canAnalyzeTier(selectedTier) && (
                <button
                  onClick={() => handleAnalyze(selectedTier)}
                  disabled={!canAnalyzeTier(selectedTier)}
                  title={tierHasData(selectedTier)
                    ? `Re-run ${TIER_LABELS[selectedTier]} analysis (overwrites existing)`
                    : `Run ${TIER_LABELS[selectedTier]} analysis`
                  }
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    analyzeMutation.isPending
                      ? "bg-blue-800 text-blue-300 cursor-wait"
                      : "bg-blue-600 text-white hover:bg-blue-500"
                  }`}
                >
                  {getAnalyzeLabel(selectedTier)}
                </button>
              )}
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
          {isLiveTier && !formula ? (
            <div className="h-48 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
              <p className="text-gray-500 text-sm">
                {hardwareConnected
                  ? "Waiting for Pioneer phrase analysis data..."
                  : "Connect Pioneer hardware to use Live tier"}
              </p>
              <p className="text-gray-600 text-xs max-w-md text-center">
                Live tier constructs arrangement analysis from Pioneer hardware data
                streaming over Ethernet — no audio files needed.
              </p>
              {hardwareConnected && (
                <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              )}
            </div>
          ) : isLoading && !isLiveTier ? (
            <div className="h-64 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
              <p className="text-gray-500 text-sm">Loading strata data...</p>
            </div>
          ) : !hasAnyData && !activeJobId ? (
            <EmptyState onAnalyze={() => handleAnalyze("quick")} isAnalyzing={analyzeMutation.isPending} />
          ) : activeJobId && activeJobTier && !formula ? (
            /* Progress replaces empty state when job is active and no data yet */
            <StrataJobProgress
              jobId={activeJobId}
              tier={activeJobTier}
              onComplete={handleJobComplete}
              onCancel={handleJobCancel}
            />
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
            <>
              {/* Show progress above results when re-running */}
              {activeJobId && activeJobTier && (
                <StrataJobProgress
                  jobId={activeJobId}
                  tier={activeJobTier}
                  onComplete={handleJobComplete}
                  onCancel={handleJobCancel}
                />
              )}
              <FormulaView
                formula={formula}
                fingerprint={fingerprint}
                tier={selectedTier}
                editMode={pageMode === "edit"}
                onExitEdit={() => setPageMode("view")}
                playbackCursorTime={isLiveTier ? livePlaybackTime : null}
              />
            </>
          ) : !activeJobId ? (
            <TierEmptyState
              tier={selectedTier}
              canAnalyze={canAnalyzeTier(selectedTier)}
              onAnalyze={() => handleAnalyze(selectedTier)}
              isAnalyzing={analyzeMutation.isPending}
              hardwareConnected={hardwareConnected}
              tierHasData={tierHasData(selectedTier)}
              analyzeLabel={getAnalyzeLabel(selectedTier)}
            />
          ) : null}
        </div>
      ) : pageMode !== "batch" && !isLiveTier ? (
        <div className="h-40 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-500 text-sm">
            Select a track above to view arrangement analysis
          </p>
        </div>
      ) : null}
    </div>
  );
}

/** Empty state when no strata data exists at all for the track. */
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

/** Empty state for a specific tier that has no data yet. */
function TierEmptyState({
  tier,
  canAnalyze,
  onAnalyze,
  isAnalyzing,
  hardwareConnected,
  tierHasData: _tierHasData,
  analyzeLabel,
}: {
  tier: StrataTier;
  canAnalyze: boolean;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  hardwareConnected: boolean;
  tierHasData: boolean;
  analyzeLabel: string;
}) {
  const isDeep = tier === "deep";

  return (
    <div className="h-48 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
      <p className="text-gray-500 text-sm">
        No data for {TIER_LABELS[tier]} tier yet.
      </p>

      {isDeep && !hardwareConnected ? (
        <p className="text-gray-600 text-xs">
          Deep tier requires Pioneer hardware connection.
        </p>
      ) : isDeep ? (
        <p className="text-gray-600 text-xs">
          Deep tier analysis is not yet available (coming in Phase 6).
        </p>
      ) : (
        <>
          <p className="text-gray-600 text-xs">
            {TIER_DESCRIPTIONS[tier]}
          </p>
          <button
            onClick={onAnalyze}
            disabled={!canAnalyze || isAnalyzing}
            className={`px-4 py-1.5 text-sm rounded transition-colors ${
              !canAnalyze || isAnalyzing
                ? "bg-blue-800 text-blue-300 cursor-wait"
                : "bg-blue-600 text-white hover:bg-blue-500"
            }`}
          >
            {isAnalyzing ? "Analyzing..." : analyzeLabel}
          </button>
        </>
      )}
    </div>
  );
}

/** Batch analysis panel. */
function BatchPanel({
  selectedCount,
  batchTiers,
  onToggleTier,
  onAnalyze,
  isAnalyzing,
  batchId,
  onBatchComplete,
  hardwareConnected,
}: {
  selectedCount: number;
  batchTiers: Set<StrataTier>;
  onToggleTier: (tier: StrataTier) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  batchId: string | null;
  onBatchComplete: () => void;
  hardwareConnected: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 px-4 py-3 bg-gray-950 rounded border border-gray-800">
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-400">Batch tiers:</span>
        {(["quick", "standard", "deep"] as StrataTier[]).map((tier) => {
          const isDeep = tier === "deep";
          const disabled = isDeep && !hardwareConnected;
          return (
            <label
              key={tier}
              className={`flex items-center gap-1.5 text-sm cursor-pointer ${
                disabled ? "text-gray-600 cursor-not-allowed" : "text-gray-300"
              }`}
            >
              <input
                type="checkbox"
                checked={batchTiers.has(tier)}
                onChange={() => !disabled && onToggleTier(tier)}
                disabled={disabled}
                className="accent-blue-500"
              />
              {TIER_LABELS[tier]}
              {isDeep && !hardwareConnected && (
                <span className="text-xs text-gray-600">(no hardware)</span>
              )}
            </label>
          );
        })}

        <button
          onClick={onAnalyze}
          disabled={selectedCount === 0 || batchTiers.size === 0 || isAnalyzing || !!batchId}
          className={`ml-auto px-4 py-1.5 text-sm rounded transition-colors ${
            selectedCount === 0 || batchTiers.size === 0 || isAnalyzing || batchId
              ? "bg-gray-800 text-gray-600 cursor-not-allowed"
              : "bg-blue-600 text-white hover:bg-blue-500"
          }`}
        >
          {isAnalyzing ? "Starting..." : `Analyze ${selectedCount} track${selectedCount !== 1 ? "s" : ""}`}
        </button>
      </div>

      {batchId && (
        <StrataBatchProgress batchId={batchId} onComplete={onBatchComplete} />
      )}
    </div>
  );
}

interface FormulaViewProps {
  formula: ArrangementFormula;
  fingerprint: string;
  tier: StrataTier;
  editMode: boolean;
  onExitEdit: () => void;
  /** Real-time playback cursor position in seconds (live tier only). */
  playbackCursorTime?: number | null;
}

function FormulaView({ formula, fingerprint, tier, editMode, onExitEdit, playbackCursorTime }: FormulaViewProps) {
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

  // Collect events for overlay: prefer per-stem strata events, fall back to M7 track-level events
  const allStemEvents: AtomicEvent[] = useMemo(() => {
    const strataEvents = displayFormula.stems.flatMap((s) => s.events);
    if (strataEvents.length > 0) return strataEvents;
    // Fall back to M7 track-level events (convert MusicalEvent → AtomicEvent shape)
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
        visibleEventTypes={visibleEventTypes}
        showStemWaveforms={showStemWaveforms}
        showPatternBlocks={showPatternBlocks}
        externalEvents={allStemEvents}
        playbackCursorTime={playbackCursorTime ?? undefined}
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
                  {s.section_start.toFixed(1)}s\u2013{s.section_end.toFixed(1)}s
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
