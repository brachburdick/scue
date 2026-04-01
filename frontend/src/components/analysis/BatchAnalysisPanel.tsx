import { StrataBatchProgress } from "../strata/TierAnalysisStatus";
import type { StrataTier } from "../../types/strata";

const TIER_LABELS: Record<StrataTier, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
  live: "Live",
  live_offline: "Live Offline",
};

interface BatchAnalysisPanelProps {
  selectedCount: number;
  batchTiers: Set<StrataTier>;
  onToggleTier: (tier: StrataTier) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  batchId: string | null;
  onBatchComplete: () => void;
  hardwareConnected: boolean;
}

export function BatchAnalysisPanel({
  selectedCount,
  batchTiers,
  onToggleTier,
  onAnalyze,
  isAnalyzing,
  batchId,
  onBatchComplete,
  hardwareConnected,
}: BatchAnalysisPanelProps) {
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
