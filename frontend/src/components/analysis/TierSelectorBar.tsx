import type { AnalysisSource, StrataTier } from "../../types/strata";

const SOURCE_LABELS: Record<AnalysisSource, string> = {
  analysis: "Original",
  pioneer_enriched: "Enriched",
  pioneer_reanalyzed: "Reanalyzed",
  pioneer_live: "Live (Pioneer)",
};

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

interface TierSelectorBarProps {
  selectedTier: StrataTier;
  onTierClick: (tier: StrataTier) => void;
  tierHasData: (tier: StrataTier) => boolean;
  hardwareConnected: boolean;
  /** Source selector state */
  selectedSource: AnalysisSource;
  onSourceChange: (source: AnalysisSource) => void;
  availableSourcesForTier: AnalysisSource[];
  /** Page mode (for compare tier selector visibility) */
  pageMode: PageMode;
  /** Compare state */
  compareTier: StrataTier;
  onCompareTierChange: (tier: StrataTier) => void;
  /** Analyze action */
  canAnalyzeTier: (tier: StrataTier) => boolean;
  onAnalyze: (tier: StrataTier) => void;
  getAnalyzeLabel: (tier: StrataTier) => string;
  isAnalyzing: boolean;
  /** Reanalyze (Pioneer grid) */
  hasV2: boolean;
  hasV3: boolean;
  onReanalyze: () => void;
  isReanalyzing: boolean;
  /** Error from analysis */
  analyzeError: Error | null;
}

export function TierSelectorBar({
  selectedTier,
  onTierClick,
  tierHasData,
  hardwareConnected,
  selectedSource,
  onSourceChange,
  availableSourcesForTier,
  pageMode,
  compareTier,
  onCompareTierChange,
  canAnalyzeTier,
  onAnalyze,
  getAnalyzeLabel,
  isAnalyzing: _isAnalyzing,
  hasV2,
  hasV3,
  onReanalyze,
  isReanalyzing,
  analyzeError,
}: TierSelectorBarProps) {
  const getTierTooltip = (tier: StrataTier): string => {
    if (tier === "deep" && !hardwareConnected) return "Requires Pioneer hardware connection";
    if (tierHasData(tier)) return TIER_DESCRIPTIONS[tier];
    return `Click to view \u2014 ${TIER_DESCRIPTIONS[tier]}`;
  };

  return (
    <div className="flex flex-col gap-2">
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
              onClick={() => onTierClick(tier)}
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
                  onClick={() => isAvailable && onCompareTierChange(tier)}
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
                onClick={() => onSourceChange(src)}
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
          {selectedTier !== "deep" && selectedTier !== "live" && canAnalyzeTier(selectedTier) && (
            <button
              onClick={() => onAnalyze(selectedTier)}
              disabled={!canAnalyzeTier(selectedTier)}
              title={tierHasData(selectedTier)
                ? `Re-run ${TIER_LABELS[selectedTier]} analysis (overwrites existing)`
                : `Run ${TIER_LABELS[selectedTier]} analysis`
              }
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                !canAnalyzeTier(selectedTier)
                  ? "bg-blue-800 text-blue-300 cursor-wait"
                  : "bg-blue-600 text-white hover:bg-blue-500"
              }`}
            >
              {getAnalyzeLabel(selectedTier)}
            </button>
          )}
          {hasV2 && !hasV3 && (
            <button
              onClick={onReanalyze}
              disabled={isReanalyzing}
              title="Re-run section & event detection with Pioneer beatgrid"
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                isReanalyzing
                  ? "bg-teal-800 text-teal-300 cursor-wait"
                  : "bg-teal-700 text-white hover:bg-teal-600"
              }`}
            >
              {isReanalyzing ? "Re-analyzing..." : "Re-analyze (Pioneer Grid)"}
            </button>
          )}
        </div>
      </div>

      {/* Error from analysis */}
      {analyzeError && (
        <div className="px-4 py-2 bg-red-950 border border-red-800 rounded text-sm text-red-300">
          Analysis failed: {analyzeError.message}
        </div>
      )}
    </div>
  );
}
