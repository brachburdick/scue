/** Lab mode view — variant comparison with substep drill-down. */

import { useState, useMemo } from "react";
import { FormulaView } from "./FormulaView";
import type { ArrangementFormula, ArrangementTransition, SubstepId, StrataTier } from "../../types/strata";

type SubstepFilter = "all" | SubstepId;
type ViewMode = "overlay" | "list";

interface LabViewProps {
  fingerprint: string;
  tier: StrataTier;
  baseFormula: ArrangementFormula;
  compareFormula: ArrangementFormula | null;
}

/** Classify which substep produced a transition. */
function transitionSubstep(t: ArrangementTransition): SubstepId {
  if (t.type === "fill") return "fill_detection";
  return "transition_detection";
}

/** Match transitions between two sets (within tolerance). */
function matchTransitions(
  base: ArrangementTransition[],
  compare: ArrangementTransition[],
  toleranceSec = 0.5,
) {
  const matched: Array<{ base: ArrangementTransition; compare: ArrangementTransition }> = [];
  const baseOnly: ArrangementTransition[] = [];
  const compareOnly: ArrangementTransition[] = [];
  const usedCompare = new Set<number>();

  for (const b of base) {
    let found = false;
    for (let i = 0; i < compare.length; i++) {
      if (usedCompare.has(i)) continue;
      if (Math.abs(b.timestamp - compare[i].timestamp) < toleranceSec && b.type === compare[i].type) {
        matched.push({ base: b, compare: compare[i] });
        usedCompare.add(i);
        found = true;
        break;
      }
    }
    if (!found) baseOnly.push(b);
  }
  for (let i = 0; i < compare.length; i++) {
    if (!usedCompare.has(i)) compareOnly.push(compare[i]);
  }
  return { matched, baseOnly, compareOnly };
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}:${s.padStart(4, "0")}`;
}

export function LabView({ fingerprint, tier, baseFormula, compareFormula }: LabViewProps) {
  const [filter, setFilter] = useState<SubstepFilter>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");

  // If no compare formula, just show the base with variant metadata
  if (!compareFormula) {
    return (
      <div className="flex flex-col gap-3">
        <VariantBadge formula={baseFormula} label="Base" color="blue" />
        <FormulaView
          formula={baseFormula}
          fingerprint={fingerprint}
          tier={tier}
          editMode={false}
          onExitEdit={() => {}}
          playbackCursorTime={null}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Diff Summary */}
      <DiffSummaryBar base={baseFormula} compare={compareFormula} />

      {/* Filter + View Mode controls */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          {(["all", "transition_detection", "energy_trend", "fill_detection"] as SubstepFilter[]).map((f) => {
            const labels: Record<SubstepFilter, string> = {
              all: "All",
              transition_detection: "Transitions",
              energy_trend: "Trends",
              fill_detection: "Fills",
            };
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2 py-0.5 text-xs rounded transition-colors ${
                  filter === f
                    ? "bg-gray-700 text-white"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {labels[f]}
              </button>
            );
          })}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1">
          {(["overlay", "list"] as ViewMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                viewMode === m
                  ? "bg-gray-700 text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {m === "overlay" ? "Overlay" : "List Diff"}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {viewMode === "list" ? (
        <TransitionListDiff
          base={baseFormula}
          compare={compareFormula}
          filter={filter}
        />
      ) : (
        <div className="flex flex-col gap-2">
          <VariantBadge formula={baseFormula} label="Base" color="blue" />
          <FormulaView
            formula={baseFormula}
            fingerprint={fingerprint}
            tier={tier}
            editMode={false}
            onExitEdit={() => {}}
            playbackCursorTime={null}
            compareTransitions={compareFormula.transitions}
          />
          <VariantBadge formula={compareFormula} label="Compare" color="purple" />
        </div>
      )}
    </div>
  );
}

function VariantBadge({ formula, label, color }: { formula: ArrangementFormula; label: string; color: "blue" | "purple" }) {
  const colorClasses = color === "blue"
    ? "bg-blue-900/30 border-blue-800 text-blue-300"
    : "bg-purple-900/30 border-purple-800 text-purple-300";
  const strategies = formula.substep_strategies ?? {};
  const strategyText = Object.entries(strategies)
    .map(([, v]) => v)
    .join(" / ");

  return (
    <div className={`px-3 py-1.5 rounded border text-xs flex items-center gap-3 ${colorClasses}`}>
      <span className="font-medium">{label}: {formula.variant ?? "default"}</span>
      {strategyText && <span className="text-gray-500">{strategyText}</span>}
      <span className="text-gray-600">
        {formula.transitions.length} transitions, {formula.patterns.length} patterns
      </span>
    </div>
  );
}

function DiffSummaryBar({ base, compare }: { base: ArrangementFormula; compare: ArrangementFormula }) {
  const diffs = [
    { label: "Transitions", base: base.transitions.length, compare: compare.transitions.length },
    { label: "Patterns", base: base.patterns.length, compare: compare.patterns.length },
    { label: "Layers", base: base.total_layers, compare: compare.total_layers },
    { label: "Complexity", base: base.arrangement_complexity, compare: compare.arrangement_complexity },
  ];

  return (
    <div className="flex items-center gap-4 px-3 py-2 bg-gray-950 rounded border border-gray-800">
      <span className="text-xs text-blue-400 font-medium">{base.variant ?? "default"}</span>
      <span className="text-gray-600 text-xs">vs</span>
      <span className="text-xs text-purple-400 font-medium">{compare.variant ?? "default"}</span>
      <div className="flex-1" />
      {diffs.map(({ label, base: b, compare: c }) => {
        const delta = typeof b === "number" && typeof c === "number" ? c - b : 0;
        const deltaStr = delta > 0 ? `+${delta}` : String(delta);
        const color = delta > 0 ? "text-green-400" : delta < 0 ? "text-red-400" : "text-gray-600";
        return (
          <span key={label} className="text-xs text-gray-500">
            {label}: <span className={color}>{deltaStr}</span>
          </span>
        );
      })}
    </div>
  );
}

function TransitionListDiff({
  base,
  compare,
  filter,
}: {
  base: ArrangementFormula;
  compare: ArrangementFormula;
  filter: SubstepFilter;
}) {
  const { matched, baseOnly, compareOnly } = useMemo(() => {
    let baseT = base.transitions;
    let compareT = compare.transitions;

    if (filter !== "all") {
      baseT = baseT.filter((t) => transitionSubstep(t) === filter);
      compareT = compareT.filter((t) => transitionSubstep(t) === filter);
    }

    return matchTransitions(baseT, compareT);
  }, [base, compare, filter]);

  return (
    <div className="grid grid-cols-3 gap-3">
      {/* Base only */}
      <div>
        <h4 className="text-xs text-blue-400 font-medium mb-2">
          Base only ({baseOnly.length})
        </h4>
        <div className="flex flex-col gap-1">
          {baseOnly.map((t, i) => (
            <TransitionCard key={i} transition={t} color="blue" />
          ))}
          {baseOnly.length === 0 && (
            <span className="text-xs text-gray-600">None</span>
          )}
        </div>
      </div>

      {/* Matched */}
      <div>
        <h4 className="text-xs text-green-400 font-medium mb-2">
          Matched ({matched.length})
        </h4>
        <div className="flex flex-col gap-1">
          {matched.map((m, i) => (
            <TransitionCard key={i} transition={m.base} color="green" />
          ))}
          {matched.length === 0 && (
            <span className="text-xs text-gray-600">None</span>
          )}
        </div>
      </div>

      {/* Compare only */}
      <div>
        <h4 className="text-xs text-purple-400 font-medium mb-2">
          Compare only ({compareOnly.length})
        </h4>
        <div className="flex flex-col gap-1">
          {compareOnly.map((t, i) => (
            <TransitionCard key={i} transition={t} color="purple" />
          ))}
          {compareOnly.length === 0 && (
            <span className="text-xs text-gray-600">None</span>
          )}
        </div>
      </div>
    </div>
  );
}

function TransitionCard({ transition, color }: { transition: ArrangementTransition; color: "blue" | "purple" | "green" }) {
  const colorClasses: Record<string, string> = {
    blue: "border-blue-900 bg-blue-950/30",
    purple: "border-purple-900 bg-purple-950/30",
    green: "border-green-900 bg-green-950/30",
  };
  return (
    <div className={`px-2 py-1 rounded border text-xs ${colorClasses[color]}`}>
      <div className="flex items-center gap-2">
        <span className="text-gray-400 font-mono">{formatTime(transition.timestamp)}</span>
        <span className="text-gray-300">{transition.type}</span>
        {transition.energy_delta !== 0 && (
          <span className={transition.energy_delta > 0 ? "text-green-500" : "text-red-500"}>
            {transition.energy_delta > 0 ? "+" : ""}{transition.energy_delta.toFixed(2)}
          </span>
        )}
      </div>
      {transition.description && (
        <div className="text-gray-600 mt-0.5">{transition.description}</div>
      )}
    </div>
  );
}
