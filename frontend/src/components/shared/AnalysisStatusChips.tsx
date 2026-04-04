import type { TrackSummary } from "../../types";

type ChipState = "complete" | "available" | "unavailable";

const CHIP_STYLES: Record<ChipState, string> = {
  complete: "bg-green-900/40 text-green-400",
  available: "bg-amber-900/40 text-amber-400",
  unavailable: "bg-gray-800/40 text-gray-600",
};

function getTierState(done: boolean | undefined, available: boolean): ChipState {
  if (done) return "complete";
  if (available) return "available";
  return "unavailable";
}

/* ── Compact variant (table rows) ──────────────────────────────── */

function CompactChip({ label, state, tooltip }: {
  label: string;
  state: ChipState;
  tooltip: string;
}) {
  return (
    <span title={tooltip} className={`px-1 py-px rounded text-[9px] font-semibold leading-tight ${CHIP_STYLES[state]}`}>
      {label}
    </span>
  );
}

function CompactSourceDot({ present, icon, tooltip }: {
  present: boolean;
  icon: string;
  tooltip: string;
}) {
  return (
    <span
      title={tooltip}
      className={`text-[10px] leading-none ${present ? "text-green-400" : "text-gray-700"}`}
    >
      {icon}
    </span>
  );
}

function CompactChips({ track }: { track: TrackSummary }) {
  const hasAudio = Boolean(track.audio_path);
  const hasPioneer = track.version >= 2 || track.source === "pioneer_enriched";

  return (
    <div className="inline-flex items-center gap-0.5 flex-nowrap">
      <CompactSourceDot present={hasAudio} icon={"\u266A"} tooltip={hasAudio ? "Audio file available" : "No audio file"} />
      <CompactSourceDot present={hasPioneer} icon={"\u25C6"} tooltip={hasPioneer ? `Pioneer data (v${track.version})` : "No Pioneer data \u2014 connect hardware or scan USB"} />
      <span className="text-gray-800 mx-px text-[9px]">|</span>
      <CompactChip label="B" state="complete" tooltip="Base analysis complete" />
      <CompactChip label="Q" state={getTierState(track.has_quick, true)} tooltip={track.has_quick ? "Quick tier complete" : "Quick tier available \u2014 fast heuristic analysis (~3-7s)"} />
      <CompactChip label="S" state={getTierState(track.has_standard, hasAudio)} tooltip={track.has_standard ? "Standard tier complete" : hasAudio ? "Standard tier available \u2014 stem separation (~1-2 min)" : "Requires audio file for stem separation"} />
      <CompactChip label="D" state={getTierState(track.has_deep, hasAudio)} tooltip={track.has_deep ? "Deep tier complete" : hasAudio ? "Deep tier available" : "Requires audio file"} />
      <CompactChip label="L" state={getTierState(track.has_live, false)} tooltip={track.has_live ? "Live tier complete" : "Requires live Pioneer hardware connection"} />
      <CompactChip label="LO" state={getTierState(track.has_live_offline, Boolean(track.has_live))} tooltip={track.has_live_offline ? "Live Offline tier complete" : track.has_live ? "Live Offline available \u2014 save live Pioneer data" : "Requires Live tier data"} />
    </div>
  );
}

/* ── Full variant (expanded rows, detail views) ────────────────── */

function DataSourceChip({ label, icon, present, tooltip }: {
  label: string;
  icon: string;
  present: boolean;
  tooltip: string;
}) {
  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${
        present ? CHIP_STYLES.complete : CHIP_STYLES.unavailable
      }`}
    >
      {icon} {label}
    </span>
  );
}

function TierChip({ label, state, tooltip }: {
  label: string;
  state: ChipState;
  tooltip: string;
}) {
  const icon = state === "complete" ? "\u2713" : state === "available" ? "\u25CB" : "\u2014";
  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${CHIP_STYLES[state]}`}
    >
      {label} {icon}
    </span>
  );
}

function FullChips({ track }: { track: TrackSummary }) {
  const hasAudio = Boolean(track.audio_path);
  const hasPioneer = track.version >= 2 || track.source === "pioneer_enriched";

  return (
    <div className="inline-flex items-center gap-1 flex-wrap">
      <DataSourceChip label="Audio" icon={"\u266A"} present={hasAudio} tooltip={hasAudio ? "Audio file available" : "No audio file"} />
      <DataSourceChip label="Pioneer" icon={"\u25C6"} present={hasPioneer} tooltip={hasPioneer ? `Pioneer data (v${track.version})` : "No Pioneer data \u2014 connect hardware or scan USB"} />
      <span className="text-gray-700 mx-0.5">|</span>
      <TierChip label="Base" state="complete" tooltip="Base analysis complete" />
      <TierChip label="Quick" state={getTierState(track.has_quick, true)} tooltip={track.has_quick ? "Quick tier complete" : "Quick tier available \u2014 fast heuristic analysis (~3-7s)"} />
      <TierChip label="Std" state={getTierState(track.has_standard, hasAudio)} tooltip={track.has_standard ? "Standard tier complete" : hasAudio ? "Standard tier available \u2014 stem separation (~1-2 min)" : "Requires audio file for stem separation"} />
      <TierChip label="Deep" state={getTierState(track.has_deep, hasAudio)} tooltip={track.has_deep ? "Deep tier complete" : hasAudio ? "Deep tier available" : "Requires audio file"} />
      <TierChip label="Live" state={getTierState(track.has_live, false)} tooltip={track.has_live ? "Live tier complete" : "Requires live Pioneer hardware connection"} />
      <TierChip label="L-O" state={getTierState(track.has_live_offline, Boolean(track.has_live))} tooltip={track.has_live_offline ? "Live Offline tier complete" : track.has_live ? "Live Offline available \u2014 save live Pioneer data" : "Requires Live tier data"} />
    </div>
  );
}

/* ── Public API ─────────────────────────────────────────────────── */

interface AnalysisStatusChipsProps {
  track: TrackSummary;
  compact?: boolean;
}

export function AnalysisStatusChips({ track, compact }: AnalysisStatusChipsProps) {
  return compact ? <CompactChips track={track} /> : <FullChips track={track} />;
}

/** Aggregate tier counts across a list of tracks. */
export function TierSummaryBar({ tracks, onFilterTier }: {
  tracks: TrackSummary[];
  onFilterTier?: (tier: string) => void;
}) {
  const total = tracks.length;
  if (total === 0) return null;

  const counts = {
    quick: tracks.filter((t) => t.has_quick).length,
    standard: tracks.filter((t) => t.has_standard).length,
    deep: tracks.filter((t) => t.has_deep).length,
    live: tracks.filter((t) => t.has_live).length,
  };

  const items: { key: string; label: string; count: number }[] = [
    { key: "quick", label: "Quick", count: counts.quick },
    { key: "standard", label: "Standard", count: counts.standard },
    { key: "deep", label: "Deep", count: counts.deep },
    { key: "live", label: "Live", count: counts.live },
  ];

  return (
    <div className="flex items-center gap-3 text-xs text-gray-400">
      {items.map(({ key, label, count }) => (
        <button
          key={key}
          onClick={() => onFilterTier?.(key)}
          className="hover:text-gray-200 transition-colors"
          title={`${count}/${total} tracks have ${label} \u2014 click to filter`}
        >
          {label}: <span className={count === total ? "text-green-400" : "text-gray-300"}>{count}</span>/{total}
        </button>
      ))}
    </div>
  );
}
