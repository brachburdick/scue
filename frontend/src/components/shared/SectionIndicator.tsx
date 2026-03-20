import type { Section } from "../../types";

const SECTION_BAR_COLORS: Record<string, string> = {
  intro: "bg-gray-500",
  verse: "bg-blue-500",
  build: "bg-yellow-500",
  drop: "bg-red-500",
  breakdown: "bg-purple-500",
  fakeout: "bg-red-400",
  outro: "bg-gray-500",
};

const SECTION_TEXT_COLORS: Record<string, string> = {
  intro: "text-gray-400",
  verse: "text-blue-400",
  build: "text-yellow-400",
  drop: "text-red-400",
  breakdown: "text-purple-400",
  fakeout: "text-red-300",
  outro: "text-gray-400",
};

function findCurrentSectionIndex(sections: Section[], positionSec: number): number {
  return sections.findIndex((s) => positionSec >= s.start && positionSec < s.end);
}

function findNextSection(sections: Section[], positionSec: number, currentIdx: number): Section | null {
  if (currentIdx >= 0 && currentIdx < sections.length - 1) {
    return sections[currentIdx + 1];
  }
  if (currentIdx < 0) {
    const next = sections.find((s) => s.start > positionSec);
    return next ?? null;
  }
  return null;
}

export interface SectionIndicatorProps {
  sections: Section[];
  positionMs: number | null;
}

export function SectionIndicator({ sections, positionMs }: SectionIndicatorProps) {
  if (!sections.length) {
    return <div className="text-gray-500 text-xs px-2 h-6 flex items-center">No sections</div>;
  }

  if (positionMs === null) {
    return <div className="text-gray-500 text-xs px-2 h-6 flex items-center">—</div>;
  }

  const positionSec = positionMs / 1000;
  const currentIdx = findCurrentSectionIndex(sections, positionSec);
  const current = currentIdx >= 0 ? sections[currentIdx] : null;
  const next = findNextSection(sections, positionSec, currentIdx);

  if (!current) {
    return (
      <div className="flex items-center gap-2 h-6 px-2">
        <span className="text-gray-500 text-xs">Between sections</span>
        {next && (
          <span className="text-gray-500 text-xs ml-auto">
            → {next.label}
          </span>
        )}
      </div>
    );
  }

  const progress = Math.min(1, Math.max(0, (positionSec - current.start) / (current.end - current.start)));
  const barColor = SECTION_BAR_COLORS[current.label] ?? "bg-gray-500";
  const textColor = SECTION_TEXT_COLORS[current.label] ?? "text-gray-400";

  return (
    <div className="flex items-center gap-2 h-6 px-2">
      <span className={`text-xs font-medium ${textColor}`}>{current.label}</span>
      <div className="h-1 rounded-full bg-gray-800 flex-1">
        <div
          className={`h-1 rounded-full ${barColor}`}
          style={{ width: `${(progress * 100).toFixed(1)}%` }}
        />
      </div>
      {next && (
        <span className="text-gray-500 text-xs">→ {next.label}</span>
      )}
    </div>
  );
}
