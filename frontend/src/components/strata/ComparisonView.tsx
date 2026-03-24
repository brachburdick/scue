import { useMemo } from "react";
import { useTrackAnalysis } from "../../api/tracks";
import { useWaveformView } from "../../hooks/useWaveformView";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import { ArrangementMap } from "./ArrangementMap";
import { DiffSummary } from "./DiffSummary";
import type { ArrangementFormula, StrataTier, SectionArrangement } from "../../types/strata";

interface ComparisonViewProps {
  fingerprint: string;
  baseTier: StrataTier;
  compareTier: StrataTier;
  baseFormula: ArrangementFormula;
  compareFormula: ArrangementFormula;
}

/** Compute diff markers between two formulas. */
function computeSectionDiffs(
  baseSections: SectionArrangement[],
  compareSections: SectionArrangement[],
): { added: Set<number>; removed: Set<number>; changed: Set<number> } {
  const baseLabels = baseSections.map((s) => `${s.section_label}@${s.section_start.toFixed(1)}`);
  const compareLabels = compareSections.map((s) => `${s.section_label}@${s.section_start.toFixed(1)}`);
  const baseSet = new Set(baseLabels);
  const compareSet = new Set(compareLabels);

  const added = new Set<number>();
  const removed = new Set<number>();
  const changed = new Set<number>();

  compareSections.forEach((s, i) => {
    const key = `${s.section_label}@${s.section_start.toFixed(1)}`;
    if (!baseSet.has(key)) added.add(i);
  });
  baseSections.forEach((s, i) => {
    const key = `${s.section_label}@${s.section_start.toFixed(1)}`;
    if (!compareSet.has(key)) removed.add(i);
  });

  // Check for label changes at same time position
  baseSections.forEach((bs, i) => {
    const cs = compareSections.find(
      (c) => Math.abs(c.section_start - bs.section_start) < 0.5
    );
    if (cs && cs.section_label !== bs.section_label) {
      changed.add(i);
    }
  });

  return { added, removed, changed };
}

function computePatternDiffs(
  baseFormula: ArrangementFormula,
  compareFormula: ArrangementFormula,
): { addedPatterns: Set<string>; removedPatterns: Set<string> } {
  const baseSigs = new Set(baseFormula.patterns.map((p) => p.template.signature || p.id));
  const compareSigs = new Set(compareFormula.patterns.map((p) => p.template.signature || p.id));

  const addedPatterns = new Set<string>();
  const removedPatterns = new Set<string>();

  compareFormula.patterns.forEach((p) => {
    const sig = p.template.signature || p.id;
    if (!baseSigs.has(sig)) addedPatterns.add(p.id);
  });
  baseFormula.patterns.forEach((p) => {
    const sig = p.template.signature || p.id;
    if (!compareSigs.has(sig)) removedPatterns.add(p.id);
  });

  return { addedPatterns, removedPatterns };
}

export function ComparisonView({
  fingerprint,
  baseTier,
  compareTier,
  baseFormula,
  compareFormula,
}: ComparisonViewProps) {
  const { data: analysis } = useTrackAnalysis(fingerprint);
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);

  const duration = analysis?.duration ?? baseFormula.sections[baseFormula.sections.length - 1]?.section_end ?? 0;
  const { viewStart, viewEnd, setView } = useWaveformView(duration);

  const waveformSections = useMemo(
    () => baseFormula.sections.map((s) => ({
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
    [baseFormula.sections],
  );

  const { addedPatterns, removedPatterns } = useMemo(
    () => computePatternDiffs(baseFormula, compareFormula),
    [baseFormula, compareFormula],
  );

  const sectionDiffs = useMemo(
    () => computeSectionDiffs(baseFormula.sections, compareFormula.sections),
    [baseFormula.sections, compareFormula.sections],
  );

  const transitionDiff = useMemo(() => {
    const baseKeys = new Set(baseFormula.transitions.map((t) => `${t.type}@${t.timestamp.toFixed(1)}`));
    const compareKeys = new Set(compareFormula.transitions.map((t) => `${t.type}@${t.timestamp.toFixed(1)}`));
    const added = compareFormula.transitions.filter((t) => !baseKeys.has(`${t.type}@${t.timestamp.toFixed(1)}`));
    const removed = baseFormula.transitions.filter((t) => !compareKeys.has(`${t.type}@${t.timestamp.toFixed(1)}`));
    return { added, removed };
  }, [baseFormula.transitions, compareFormula.transitions]);

  return (
    <div className="flex flex-col gap-4">
      <DiffSummary
        baseTier={baseTier}
        compareTier={compareTier}
        baseFormula={baseFormula}
        compareFormula={compareFormula}
      />

      {/* Shared waveform */}
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
          height={80}
          renderParams={activeRenderParams}
        />
      ) : (
        <div className="h-20 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-600 text-xs">Waveform loading...</p>
        </div>
      )}

      {/* Stacked arrangement maps */}
      <div className="flex flex-col gap-1">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-blue-400 font-semibold px-1">
            Base: {baseTier}
          </span>
          <ArrangementMap
            formula={baseFormula}
            duration={duration}
            viewStart={viewStart}
            viewEnd={viewEnd}
            onViewChange={setView}
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-purple-400 font-semibold px-1">
            Compare: {compareTier}
          </span>
          <ArrangementMap
            formula={compareFormula}
            duration={duration}
            viewStart={viewStart}
            viewEnd={viewEnd}
            onViewChange={setView}
          />
        </div>
      </div>

      {/* Diff details */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Pattern diffs */}
        <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Pattern Differences
          </span>
          <div className="mt-2 flex flex-col gap-1">
            {addedPatterns.size === 0 && removedPatterns.size === 0 ? (
              <p className="text-xs text-gray-600">No pattern differences</p>
            ) : (
              <>
                {compareFormula.patterns
                  .filter((p) => addedPatterns.has(p.id))
                  .map((p) => (
                    <div key={p.id} className="flex items-center gap-2 text-xs">
                      <span className="text-green-400">+</span>
                      <span className="text-gray-300 font-mono">{p.name}</span>
                      <span className="text-gray-600">
                        {p.instances.length} inst.
                      </span>
                    </div>
                  ))}
                {baseFormula.patterns
                  .filter((p) => removedPatterns.has(p.id))
                  .map((p) => (
                    <div key={p.id} className="flex items-center gap-2 text-xs">
                      <span className="text-red-400">-</span>
                      <span className="text-gray-300 font-mono">{p.name}</span>
                      <span className="text-gray-600">
                        {p.instances.length} inst.
                      </span>
                    </div>
                  ))}
              </>
            )}
          </div>
        </div>

        {/* Transition diffs */}
        <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Transition Differences
          </span>
          <div className="mt-2 flex flex-col gap-1">
            {transitionDiff.added.length === 0 && transitionDiff.removed.length === 0 ? (
              <p className="text-xs text-gray-600">No transition differences</p>
            ) : (
              <>
                {transitionDiff.added.map((t, i) => (
                  <div key={`a${i}`} className="flex items-center gap-2 text-xs">
                    <span className="text-green-400">+</span>
                    <span className="text-gray-500 font-mono w-12 text-right">
                      {t.timestamp.toFixed(1)}s
                    </span>
                    <span className="text-gray-300">{t.type.replace("_", " ")}</span>
                  </div>
                ))}
                {transitionDiff.removed.map((t, i) => (
                  <div key={`r${i}`} className="flex items-center gap-2 text-xs">
                    <span className="text-red-400">-</span>
                    <span className="text-gray-500 font-mono w-12 text-right">
                      {t.timestamp.toFixed(1)}s
                    </span>
                    <span className="text-gray-300">{t.type.replace("_", " ")}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Section diffs */}
        <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Section Differences
          </span>
          <div className="mt-2 flex flex-col gap-1">
            {sectionDiffs.added.size === 0 && sectionDiffs.removed.size === 0 && sectionDiffs.changed.size === 0 ? (
              <p className="text-xs text-gray-600">No section differences</p>
            ) : (
              <>
                {Array.from(sectionDiffs.added).map((idx) => {
                  const s = compareFormula.sections[idx];
                  return (
                    <div key={`a${idx}`} className="flex items-center gap-2 text-xs">
                      <span className="text-green-400">+</span>
                      <span className="text-gray-300">{s.section_label}</span>
                      <span className="text-gray-500 font-mono">
                        {s.section_start.toFixed(1)}s
                      </span>
                    </div>
                  );
                })}
                {Array.from(sectionDiffs.removed).map((idx) => {
                  const s = baseFormula.sections[idx];
                  return (
                    <div key={`r${idx}`} className="flex items-center gap-2 text-xs">
                      <span className="text-red-400">-</span>
                      <span className="text-gray-300">{s.section_label}</span>
                      <span className="text-gray-500 font-mono">
                        {s.section_start.toFixed(1)}s
                      </span>
                    </div>
                  );
                })}
                {Array.from(sectionDiffs.changed).map((idx) => {
                  const bs = baseFormula.sections[idx];
                  const cs = compareFormula.sections.find(
                    (c) => Math.abs(c.section_start - bs.section_start) < 0.5
                  );
                  return (
                    <div key={`c${idx}`} className="flex items-center gap-2 text-xs">
                      <span className="text-yellow-400">~</span>
                      <span className="text-gray-500">{bs.section_label}</span>
                      <span className="text-gray-600">&rarr;</span>
                      <span className="text-gray-300">{cs?.section_label ?? "?"}</span>
                      <span className="text-gray-500 font-mono">
                        {bs.section_start.toFixed(1)}s
                      </span>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
