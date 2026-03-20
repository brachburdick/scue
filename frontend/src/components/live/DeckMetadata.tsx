import { useCallback } from "react";
import type { PlayerInfo } from "../../types/bridge";
import type { TrackAnalysis, Section } from "../../types";

const STATE_BADGE_STYLES: Record<string, string> = {
  playing: "bg-green-900/50 text-green-300",
  paused: "bg-amber-900/50 text-amber-300",
  cued: "bg-amber-900/50 text-amber-300",
  stopped: "bg-gray-800 text-gray-400",
  searching: "bg-gray-800 text-gray-400",
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

function findCurrentSection(
  sections: Section[],
  positionMs: number | null,
): { section: Section; index: number; barInSection: number; totalBars: number; pct: number } | null {
  if (positionMs === null || !sections.length) return null;
  const sec = positionMs / 1000;
  const idx = sections.findIndex((s) => sec >= s.start && sec < s.end);
  if (idx < 0) return null;
  const s = sections[idx];
  const pct = (sec - s.start) / (s.end - s.start);
  const bar = Math.min(s.bar_count, Math.floor(pct * s.bar_count) + 1);
  return { section: s, index: idx, barInSection: bar, totalBars: s.bar_count, pct: pct * 100 };
}

function confidenceColor(c: number): string {
  if (c >= 0.8) return "text-green-400";
  if (c >= 0.5) return "text-amber-400";
  return "text-red-400";
}

function pitchColor(p: number): string {
  if (p > 0) return "text-green-400";
  if (p < 0) return "text-red-400";
  return "text-gray-400";
}

function formatPitch(p: number): string {
  if (p > 0) return `+${p.toFixed(1)}%`;
  return `${p.toFixed(1)}%`;
}

export interface DeckMetadataProps {
  player: PlayerInfo;
  analysis: TrackAnalysis | null;
}

export function DeckMetadata({ player, analysis }: DeckMetadataProps) {
  const copyFingerprint = useCallback(() => {
    if (analysis) {
      navigator.clipboard.writeText(analysis.fingerprint);
    }
  }, [analysis]);

  const stateBadge = STATE_BADGE_STYLES[player.playback_state] ?? STATE_BADGE_STYLES.stopped;

  // Bridge-only mode (no analysis)
  if (!analysis) {
    return (
      <div className="px-2 py-1.5">
        <div className="flex items-center gap-3 text-sm">
          <span className="font-mono text-gray-300">{player.bpm.toFixed(2)}</span>
          <span className={`font-mono ${pitchColor(player.pitch)}`}>{formatPitch(player.pitch)}</span>
          <span className={`px-2 py-0.5 rounded text-xs ${stateBadge}`}>{player.playback_state}</span>
          <span className={`inline-block w-2 h-2 rounded-full ${player.is_on_air ? "bg-green-500" : "bg-gray-600"}`} />
          <span className="font-mono text-xs text-gray-500">rb:{player.rekordbox_id}</span>
          <span className="font-mono text-xs text-gray-400">Beat {player.beat_within_bar}/4</span>
        </div>
      </div>
    );
  }

  const sectionInfo = findCurrentSection(analysis.sections, player.playback_position_ms);

  return (
    <div className="px-2 py-1.5">
      {/* Primary row */}
      <div className="flex items-center gap-3 text-sm">
        <span className="text-white font-medium truncate max-w-[200px]">{analysis.title}</span>
        <span className="text-gray-300 truncate max-w-[160px]">{analysis.artist}</span>
        <span className="font-mono text-gray-300">{player.bpm.toFixed(2)}</span>
        {analysis.bpm !== player.bpm && (
          <span className="font-mono text-xs text-gray-500">(orig: {analysis.bpm.toFixed(2)})</span>
        )}
        <span className={`font-mono ${pitchColor(player.pitch)}`}>{formatPitch(player.pitch)}</span>
        {analysis.features?.key && (
          <span className="text-gray-300">{analysis.features.key}</span>
        )}
        <span className={`px-2 py-0.5 rounded text-xs ${stateBadge}`}>{player.playback_state}</span>
        <span className={`inline-block w-2 h-2 rounded-full ${player.is_on_air ? "bg-green-500" : "bg-gray-600"}`} />
      </div>

      {/* Secondary row */}
      <div className="flex items-center gap-3 mt-1 flex-wrap">
        {sectionInfo && (
          <>
            <span className={`text-xs ${SECTION_TEXT_COLORS[sectionInfo.section.label] ?? "text-gray-400"}`}>
              {sectionInfo.section.label} (bar {sectionInfo.barInSection}/{sectionInfo.totalBars}, {sectionInfo.pct.toFixed(0)}%)
            </span>
            <span className={`text-xs ${confidenceColor(sectionInfo.section.confidence)}`}>
              {sectionInfo.section.confidence.toFixed(2)}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
              {sectionInfo.section.source}
            </span>
          </>
        )}
        <span
          className="font-mono text-xs text-gray-500 cursor-pointer hover:text-gray-300"
          onClick={copyFingerprint}
          title={analysis.fingerprint}
        >
          {analysis.fingerprint.slice(0, 12)}
        </span>
        <span className="font-mono text-xs text-gray-500">rb:{player.rekordbox_id}</span>
        <span className="text-xs text-gray-500">Player {player.track_source_player}</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
          {player.track_source_slot}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
          {analysis.source}
        </span>
        <span className="font-mono text-xs text-gray-400">Beat {player.beat_within_bar}/4</span>
      </div>
    </div>
  );
}
