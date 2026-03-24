/**
 * LiveEventDisplay — shared "what's happening now" component.
 *
 * Consumes ActiveEventState from useActiveEvents hook and renders:
 * - Current section with progress and phrase position
 * - Recently-fired event indicators (flash + fade)
 * - Upcoming event preview
 *
 * Reusable across annotation page, live deck monitor, analysis viewer.
 */

import { useMemo } from "react";
import { EVENT_COLORS } from "../../types/events";
import type { EventType } from "../../types/events";
import type { ActiveEventState, FiredEvent, EventPreview } from "../../types/activeEvents";

// --- Section colors (Tailwind classes, match SectionIndicator) ---

const SECTION_BG: Record<string, string> = {
  intro: "bg-gray-700/40",
  verse: "bg-blue-800/40",
  build: "bg-yellow-800/40",
  drop: "bg-red-800/40",
  breakdown: "bg-purple-800/40",
  fakeout: "bg-orange-800/40",
  outro: "bg-gray-700/40",
};

const SECTION_TEXT: Record<string, string> = {
  intro: "text-gray-300",
  verse: "text-blue-300",
  build: "text-yellow-300",
  drop: "text-red-300",
  breakdown: "text-purple-300",
  fakeout: "text-orange-300",
  outro: "text-gray-300",
};

// --- Event type indicators ---

const EVENT_LABELS: Record<EventType, string> = {
  kick: "KICK",
  snare: "SNR",
  clap: "CLAP",
  hihat: "HH",
  riser: "▲ RSR",
  faller: "▼ FLR",
  stab: "◆ STB",
};

// --- Component ---

export interface LiveEventDisplayProps {
  state: ActiveEventState | null;
  layout?: "horizontal" | "vertical";
  className?: string;
}

export function LiveEventDisplay({
  state,
  layout = "horizontal",
  className = "",
}: LiveEventDisplayProps) {
  if (!state) {
    return (
      <div className={`text-gray-600 text-xs px-3 py-2 ${className}`}>
        No playback
      </div>
    );
  }

  const isHorizontal = layout === "horizontal";

  return (
    <div
      className={`
        rounded border border-gray-800 bg-gray-950/80
        ${isHorizontal ? "flex items-center gap-3 px-3 py-1.5" : "flex flex-col gap-1.5 px-3 py-2"}
        ${className}
      `}
    >
      <SectionBand state={state} horizontal={isHorizontal} />
      <EventIndicators
        recentEvents={state.recentEvents}
        horizontal={isHorizontal}
      />
      <UpcomingPreview
        upcomingEvents={state.upcomingEvents}
        horizontal={isHorizontal}
      />
    </div>
  );
}

// --- Section band ---

function SectionBand({
  state,
  horizontal,
}: {
  state: ActiveEventState;
  horizontal: boolean;
}) {
  const { activeSections, phrase } = state;
  const section = activeSections[0] ?? null;

  if (!section) {
    return (
      <div
        className={`text-gray-500 text-xs ${horizontal ? "min-w-[120px]" : ""}`}
      >
        Between sections
      </div>
    );
  }

  const progress = Math.min(
    1,
    Math.max(0, (state.currentTime - section.start) / (section.end - section.start)),
  );
  const bg = SECTION_BG[section.label] ?? "bg-gray-700/40";
  const text = SECTION_TEXT[section.label] ?? "text-gray-300";

  const phraseLabel = phrase
    ? `bar ${phrase.barInPhrase + 1}/${phrase.phraseLength}`
    : null;

  return (
    <div
      className={`
        rounded px-2 py-1 ${bg} relative overflow-hidden
        ${horizontal ? "min-w-[120px]" : ""}
      `}
    >
      {/* Progress underlay */}
      <div
        className="absolute inset-y-0 left-0 bg-white/5"
        style={{ width: `${(progress * 100).toFixed(1)}%` }}
      />
      <div className="relative flex items-center justify-between gap-2">
        <span className={`text-xs font-semibold uppercase tracking-wide ${text}`}>
          {section.label}
        </span>
        {phraseLabel && (
          <span className="text-[10px] text-gray-500 font-mono">{phraseLabel}</span>
        )}
      </div>
    </div>
  );
}

// --- Event indicators ---

function EventIndicators({
  recentEvents,
  horizontal,
}: {
  recentEvents: FiredEvent[];
  horizontal: boolean;
}) {
  // Deduplicate: show one indicator per type, with the freshest age
  const byType = useMemo(() => {
    const map = new Map<EventType, FiredEvent>();
    for (const e of recentEvents) {
      const existing = map.get(e.type);
      if (!existing || e.age < existing.age) {
        map.set(e.type, e);
      }
    }
    return Array.from(map.values()).sort((a, b) => a.age - b.age);
  }, [recentEvents]);

  if (byType.length === 0) {
    return (
      <div
        className={`text-gray-700 text-xs ${horizontal ? "flex-1 text-center" : ""}`}
      >
        —
      </div>
    );
  }

  return (
    <div
      className={`
        ${horizontal ? "flex items-center gap-2 flex-1" : "flex flex-col gap-0.5"}
      `}
    >
      {byType.map((e) => (
        <EventDot key={e.type} event={e} />
      ))}
    </div>
  );
}

function EventDot({ event }: { event: FiredEvent }) {
  // Opacity: 1.0 at age=0, 0.2 at age=recentWindow
  const opacity = Math.max(0.2, 1 - event.age / 300);
  const color = EVENT_COLORS[event.type] ?? "#888";

  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-mono transition-opacity duration-100"
      style={{ opacity }}
    >
      <span
        className="inline-block w-2 h-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span style={{ color }}>{EVENT_LABELS[event.type]}</span>
    </span>
  );
}

// --- Upcoming preview ---

function UpcomingPreview({
  upcomingEvents,
  horizontal,
}: {
  upcomingEvents: EventPreview[];
  horizontal: boolean;
}) {
  // Only show first upcoming event within 2 seconds
  const next = upcomingEvents.find((e) => e.timeUntil <= 2.0) ?? null;

  if (!next) {
    return horizontal ? null : (
      <div className="text-gray-700 text-[10px]">—</div>
    );
  }

  const color = EVENT_COLORS[next.type] ?? "#888";

  return (
    <div
      className={`text-[10px] text-gray-500 font-mono ${horizontal ? "ml-auto whitespace-nowrap" : ""}`}
    >
      <span style={{ color }}>{EVENT_LABELS[next.type]}</span>
      <span className="text-gray-600"> in {next.timeUntil.toFixed(1)}s</span>
    </div>
  );
}
