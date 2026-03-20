import { useState, useRef, useEffect } from "react";
import type { Section, SectionLabel } from "../../types";

const SECTION_LABEL_COLORS: Record<string, string> = {
  intro: "text-gray-400",
  verse: "text-blue-400",
  build: "text-yellow-400",
  drop: "text-red-400",
  breakdown: "text-purple-400",
  fakeout: "text-red-300",
  outro: "text-gray-400",
};

const ALL_LABELS: SectionLabel[] = ["intro", "verse", "build", "drop", "breakdown", "fakeout", "outro"];

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

function confidenceColor(c: number): string {
  if (c < 0.5) return "text-red-400";
  if (c < 0.7) return "text-yellow-400";
  return "text-green-400";
}

interface SectionListProps {
  sections: Section[];
  highlightedIndex: number | null;
  selectedIndex: number | null;
  onHover: (index: number | null) => void;
  onSelect: (index: number) => void;
}

export function SectionList({
  sections,
  highlightedIndex,
  selectedIndex,
  onHover,
  onSelect,
}: SectionListProps) {
  const [filter, setFilter] = useState<Set<SectionLabel>>(new Set());
  const listRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  // Auto-scroll to selected row
  useEffect(() => {
    if (selectedIndex == null) return;
    const row = rowRefs.current.get(selectedIndex);
    row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedIndex]);

  const toggleFilter = (label: SectionLabel) => {
    setFilter((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  const resetFilter = () => setFilter(new Set());

  const filtered = filter.size === 0
    ? sections
    : sections.filter((s) => filter.has(s.label as SectionLabel));

  // Map filtered indices back to original indices
  const originalIndices = filter.size === 0
    ? sections.map((_, i) => i)
    : sections.reduce<number[]>((acc, s, i) => {
        if (filter.has(s.label as SectionLabel)) acc.push(i);
        return acc;
      }, []);

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap gap-1 mb-2">
        <button
          className={`px-2 py-0.5 rounded text-xs transition-colors ${
            filter.size === 0
              ? "bg-gray-700 text-white"
              : "bg-gray-800 text-gray-500 hover:text-gray-300"
          }`}
          onClick={resetFilter}
        >
          All
        </button>
        {ALL_LABELS.map((label) => (
          <button
            key={label}
            className={`px-2 py-0.5 rounded text-xs transition-colors ${
              filter.has(label)
                ? "bg-gray-700 text-white"
                : "bg-gray-800 text-gray-500 hover:text-gray-300"
            }`}
            onClick={() => toggleFilter(label)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Section rows */}
      <div ref={listRef} className="max-h-64 overflow-auto rounded border border-gray-800">
        {filtered.length === 0 ? (
          <p className="px-3 py-4 text-center text-gray-500 text-sm">No sections detected</p>
        ) : (
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-gray-800 bg-gray-900">
                <th className="px-2 py-1 text-left text-gray-400 font-medium">#</th>
                <th className="px-2 py-1 text-left text-gray-400 font-medium">Label</th>
                <th className="px-2 py-1 text-left text-gray-400 font-medium">Start</th>
                <th className="px-2 py-1 text-left text-gray-400 font-medium">End</th>
                <th className="px-2 py-1 text-left text-gray-400 font-medium">Bars</th>
                <th className="px-2 py-1 text-left text-gray-400 font-medium">Conf</th>
                <th className="px-2 py-1 text-left text-gray-400 font-medium">Src</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((sec, fi) => {
                const origIdx = originalIndices[fi];
                const isHighlighted = highlightedIndex === origIdx;
                const isSelected = selectedIndex === origIdx;
                const irregular = sec.irregular_phrase;

                return (
                  <tr
                    key={origIdx}
                    ref={(el) => {
                      if (el) rowRefs.current.set(origIdx, el);
                      else rowRefs.current.delete(origIdx);
                    }}
                    className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-blue-900/30"
                        : isHighlighted
                          ? "bg-gray-800/50"
                          : "hover:bg-gray-800/30"
                    }`}
                    onMouseEnter={() => onHover(origIdx)}
                    onMouseLeave={() => onHover(null)}
                    onClick={() => onSelect(origIdx)}
                  >
                    <td className="px-2 py-1 text-gray-500">{origIdx + 1}</td>
                    <td className={`px-2 py-1 font-medium ${SECTION_LABEL_COLORS[sec.label] ?? "text-gray-400"}`}>
                      {sec.label}
                    </td>
                    <td className="px-2 py-1 text-gray-300">{formatTime(sec.start)}</td>
                    <td className="px-2 py-1 text-gray-300">{formatTime(sec.end)}</td>
                    <td className={`px-2 py-1 ${irregular ? "text-yellow-400" : "text-gray-300"}`}>
                      {sec.bar_count}/{sec.expected_bar_count}
                    </td>
                    <td className={`px-2 py-1 ${confidenceColor(sec.confidence)}`}>
                      {sec.confidence.toFixed(2)}
                    </td>
                    <td className="px-2 py-1">
                      <span
                        className={`px-1 py-0.5 rounded text-[10px] ${
                          sec.source === "pioneer_enriched"
                            ? "bg-green-900/50 text-green-300"
                            : "bg-gray-800 text-gray-500"
                        }`}
                      >
                        {sec.source === "pioneer_enriched" ? "pio" : "ana"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
