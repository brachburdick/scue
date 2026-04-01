import { useState, useMemo, useCallback, useEffect } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { TrackPicker } from "../components/analysis/TrackPicker";
import { WaveformPanel } from "../components/analysis/WaveformPanel";
import { TierSelectorBar } from "../components/analysis/TierSelectorBar";
import { FormulaView } from "../components/analysis/FormulaView";
import { BatchAnalysisPanel } from "../components/analysis/BatchAnalysisPanel";
import { ComparisonView } from "../components/strata/ComparisonView";
import { StrataJobProgress } from "../components/strata/TierAnalysisStatus";
import {
  useStrataAllTiers,
  useAnalyzeStrata,
  useReanalyze,
  useTrackVersions,
  useAnalyzeStrataBatch,
  useLiveStrata,
} from "../api/strata";
import { apiFetch } from "../api/client";
import { useBridgeStore } from "../stores/bridgeStore";
import { useStrataLiveStore } from "../stores/strataLiveStore";
import type { AnalysisSource, ArrangementFormula, StrataTier } from "../types/strata";

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

type PageMode = "view" | "edit" | "compare" | "batch";

export function AnalysisPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  // URL params for deep linking
  const urlTrack = searchParams.get("track");
  const urlTier = searchParams.get("tier") as StrataTier | null;
  const urlSource = searchParams.get("source") as AnalysisSource | null;

  const [fingerprint, setFingerprint] = useState<string | null>(urlTrack);
  const [selectedTier, setSelectedTier] = useState<StrataTier>(urlTier ?? "quick");
  const [selectedSource, setSelectedSource] = useState<AnalysisSource>(urlSource ?? "analysis");
  const [pageMode, setPageMode] = useState<PageMode>("view");
  const [compareTier, setCompareTier] = useState<StrataTier>("standard");
  const [compareSource, _setCompareSource] = useState<AnalysisSource>("analysis");
  const [waveformCollapsed, setWaveformCollapsed] = useState(false);

  // Apply URL params on mount
  useEffect(() => {
    if (urlTrack && urlTrack !== fingerprint) setFingerprint(urlTrack);
    if (urlTier) setSelectedTier(urlTier);
    if (urlSource) setSelectedSource(urlSource);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Data fetching
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

  const liveFormulas = useMemo(() => {
    const merged: Record<number, ArrangementFormula> = {};
    if (restLiveData?.players) {
      for (const [pn, f] of Object.entries(restLiveData.players)) {
        merged[Number(pn)] = f;
      }
    }
    for (const [pn, f] of Object.entries(wsLiveFormulas)) {
      merged[Number(pn)] = f;
    }
    return merged;
  }, [restLiveData, wsLiveFormulas]);

  const hasLiveData = Object.keys(liveFormulas).length > 0;

  const livePlayerNumber = useMemo(() => {
    const playerNums = Object.keys(liveFormulas).map(Number);
    if (playerNums.length === 0) return null;
    const onAir = playerNums.find((pn) => players[String(pn)]?.is_on_air);
    return onAir ?? playerNums[0];
  }, [liveFormulas, players]);

  const liveFormula: ArrangementFormula | null = livePlayerNumber != null ? liveFormulas[livePlayerNumber] ?? null : null;

  const livePlaybackTime = useMemo(() => {
    if (livePlayerNumber == null) return null;
    const player = players[String(livePlayerNumber)];
    if (!player?.playback_position_ms) return null;
    return player.playback_position_ms / 1000;
  }, [livePlayerNumber, players]);

  const isLiveTier = selectedTier === "live";

  const availableTiers = data?.available_tiers ?? [];
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

  const tierHasData = useCallback((tier: StrataTier) =>
    tier === "live" ? hasLiveData || availableTiers.includes("live") : availableTiers.includes(tier),
    [hasLiveData, availableTiers],
  );

  const handleAnalyze = useCallback((tier: StrataTier) => {
    analyzeMutation.mutate(
      { tiers: [tier] },
      {
        onSuccess: (result) => {
          if (result.job_id) {
            setActiveJobId(result.job_id);
            setActiveJobTier(tier);
          } else {
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
    for (const fp of selectedFingerprints) {
      queryClient.invalidateQueries({ queryKey: ["strata", fp] });
    }
    if (fingerprint) refetch();
  }, [selectedFingerprints, fingerprint, refetch, queryClient]);

  const handleTierClick = useCallback((tier: StrataTier) => {
    setSelectedTier(tier);
    if (pageMode === "batch") return;
  }, [pageMode]);

  const getAnalyzeLabel = (tier: StrataTier): string => {
    if (analyzeMutation.isPending && activeJobTier === tier) return "Analyzing...";
    if (tierHasData(tier)) return `Re-run ${TIER_LABELS[tier]} (overwrites)`;
    return `Analyze ${TIER_LABELS[tier]}`;
  };

  const canAnalyzeTier = (tier: StrataTier): boolean => {
    if (analyzeMutation.isPending || activeJobId !== null) return false;
    if (tier === "deep" && !hardwareConnected) return false;
    return true;
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/library" className="text-sm text-gray-500 hover:text-gray-300 transition-colors">
            &larr; Library
          </Link>
          <h1 className="text-xl font-semibold">Analysis</h1>
        </div>
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

      {/* Track Picker */}
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
        <BatchAnalysisPanel
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
          {/* Waveform Panel (collapsible) */}
          {fingerprint && (
            <WaveformPanel
              fingerprint={fingerprint}
              collapsed={waveformCollapsed}
              onToggleCollapse={() => setWaveformCollapsed((v) => !v)}
            />
          )}

          {/* Tier Selector */}
          <TierSelectorBar
            selectedTier={selectedTier}
            onTierClick={handleTierClick}
            tierHasData={tierHasData}
            hardwareConnected={hardwareConnected}
            selectedSource={selectedSource}
            onSourceChange={setSelectedSource}
            availableSourcesForTier={availableSourcesForTier}
            pageMode={pageMode}
            compareTier={compareTier}
            onCompareTierChange={setCompareTier}
            canAnalyzeTier={canAnalyzeTier}
            onAnalyze={handleAnalyze}
            getAnalyzeLabel={getAnalyzeLabel}
            isAnalyzing={analyzeMutation.isPending}
            hasV2={hasV2}
            hasV3={hasV3}
            onReanalyze={() => reanalyzeMutation.mutate(undefined, { onSuccess: () => refetch() })}
            isReanalyzing={reanalyzeMutation.isPending}
            analyzeError={analyzeMutation.isError ? analyzeMutation.error : null}
          />

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
                streaming over Ethernet &mdash; no audio files needed.
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
            <StrataJobProgress
              jobId={activeJobId}
              tier={activeJobTier}
              onComplete={handleJobComplete}
              onCancel={handleJobCancel}
            />
          ) : pageMode === "compare" && formula && compareFormula ? (
            <ComparisonView
              fingerprint={fingerprint!}
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
                fingerprint={fingerprint!}
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

function TierEmptyState({
  tier,
  canAnalyze,
  onAnalyze,
  isAnalyzing,
  hardwareConnected,
}: {
  tier: StrataTier;
  canAnalyze: boolean;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  hardwareConnected: boolean;
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
            {isAnalyzing ? "Analyzing..." : `Analyze ${TIER_LABELS[tier]}`}
          </button>
        </>
      )}
    </div>
  );
}
