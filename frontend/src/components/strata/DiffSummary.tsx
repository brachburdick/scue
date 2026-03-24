import type { ArrangementFormula, StrataTier } from "../../types/strata";

interface DiffSummaryProps {
  baseTier: StrataTier;
  compareTier: StrataTier;
  baseFormula: ArrangementFormula;
  compareFormula: ArrangementFormula;
}

function Delta({ label, base, compare, decimals }: {
  label: string;
  base: number;
  compare: number;
  decimals?: number;
}) {
  const d = decimals ?? 0;
  const diff = compare - base;
  const diffStr = diff > 0 ? `+${diff.toFixed(d)}` : diff.toFixed(d);
  const color = diff > 0 ? "text-green-400" : diff < 0 ? "text-red-400" : "text-gray-500";
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-gray-500 text-xs">{label}:</span>
      <span className="text-gray-300 text-sm font-mono">
        {base.toFixed(d)}
      </span>
      <span className="text-gray-600 text-xs">&rarr;</span>
      <span className="text-gray-300 text-sm font-mono">
        {compare.toFixed(d)}
      </span>
      <span className={`text-xs font-mono ${color}`}>
        ({diffStr})
      </span>
    </div>
  );
}

export function DiffSummary({ baseTier, compareTier, baseFormula, compareFormula }: DiffSummaryProps) {
  return (
    <div className="flex items-center gap-6 px-4 py-2 bg-gray-950 rounded border border-gray-800 flex-wrap">
      <div className="flex items-center gap-1 text-xs">
        <span className="text-gray-500">Comparing</span>
        <span className="text-blue-400 font-semibold">{baseTier}</span>
        <span className="text-gray-600">vs</span>
        <span className="text-purple-400 font-semibold">{compareTier}</span>
      </div>
      <Delta
        label="Patterns"
        base={baseFormula.total_patterns}
        compare={compareFormula.total_patterns}
      />
      <Delta
        label="Transitions"
        base={baseFormula.transitions.length}
        compare={compareFormula.transitions.length}
      />
      <Delta
        label="Layers"
        base={baseFormula.total_layers}
        compare={compareFormula.total_layers}
      />
      <Delta
        label="Complexity"
        base={baseFormula.arrangement_complexity}
        compare={compareFormula.arrangement_complexity}
        decimals={2}
      />
    </div>
  );
}
