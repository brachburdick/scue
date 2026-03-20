import type { PlayerInfo } from "../../types/bridge";
import { useResolveTrack } from "../../api/tracks";
import { useTrackAnalysis } from "../../api/tracks";
import { DeckWaveform } from "./DeckWaveform";
import { DeckMetadata } from "./DeckMetadata";
import { DeckEmptyState } from "./DeckEmptyState";
import { SectionIndicator } from "../shared/SectionIndicator";
import type { EmptyStateKind } from "./DeckEmptyState";

export interface DeckPanelProps {
  deckNumber: 1 | 2;
  player: PlayerInfo | undefined;
  bridgeOverride: EmptyStateKind | null;
}

export function DeckPanel({ deckNumber, player, bridgeOverride }: DeckPanelProps) {
  const rbId = player?.rekordbox_id ?? null;
  const srcPlayer = player?.track_source_player ?? 0;
  const srcSlot = player?.track_source_slot ?? "";

  const resolve = useResolveTrack(srcPlayer, srcSlot, rbId && rbId > 0 ? rbId : null);
  const fingerprint = resolve.data?.fingerprint ?? null;
  const analysis = useTrackAnalysis(fingerprint);

  // Header
  const stateLabel = player?.playback_state ?? "";
  const stateBadge =
    stateLabel === "playing"
      ? "bg-green-900/50 text-green-300"
      : stateLabel === "paused" || stateLabel === "cued"
        ? "bg-amber-900/50 text-amber-300"
        : "bg-gray-800 text-gray-400";

  return (
    <div className="rounded border border-gray-800 bg-gray-950 p-3 flex flex-col flex-1 min-h-0">
      {/* Header bar */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Deck {deckNumber}
        </span>
        <div className="flex items-center gap-2">
          {player && (
            <>
              <span className={`px-2 py-0.5 rounded text-xs ${stateBadge}`}>
                {stateLabel}
              </span>
              <span
                className={`inline-block w-2 h-2 rounded-full ${player.is_on_air ? "bg-green-500" : "bg-gray-600"}`}
              />
            </>
          )}
        </div>
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  );

  function renderContent() {
    // Bridge-level overrides
    if (bridgeOverride) {
      return <DeckEmptyState kind={bridgeOverride} deckNumber={deckNumber} />;
    }

    // D1: No player data
    if (!player) {
      return <DeckEmptyState kind="no-player" deckNumber={deckNumber} />;
    }

    // D2: No track loaded
    if (!rbId || rbId === 0) {
      return <DeckEmptyState kind="no-track" deckNumber={deckNumber} />;
    }

    // D3: Resolution pending
    if (resolve.isLoading) {
      return <DeckEmptyState kind="resolving" deckNumber={deckNumber} />;
    }

    // D4: Not found
    if (resolve.isError || (!resolve.isLoading && !fingerprint)) {
      return (
        <>
          <DeckEmptyState
            kind="not-found"
            deckNumber={deckNumber}
            rekordboxId={rbId}
            sourcePlayer={srcPlayer}
            sourceSlot={srcSlot}
          />
          <DeckMetadata player={player} analysis={null} />
        </>
      );
    }

    // D5: Analysis loading
    if (analysis.isLoading) {
      return <DeckEmptyState kind="loading-analysis" deckNumber={deckNumber} />;
    }

    const track = analysis.data ?? null;

    // D7: No waveform
    if (track && !track.waveform) {
      return (
        <>
          <DeckEmptyState kind="no-waveform" deckNumber={deckNumber} />
          <DeckMetadata player={player} analysis={track} />
          <SectionIndicator sections={track.sections} positionMs={player.playback_position_ms} />
        </>
      );
    }

    // D6: Full data (D8 handled by SectionIndicator showing "No sections")
    if (track && track.waveform) {
      return (
        <>
          <DeckWaveform
            waveform={track.waveform}
            sections={track.sections}
            duration={track.duration}
            positionMs={player.playback_position_ms}
          />
          <DeckMetadata player={player} analysis={track} />
          <SectionIndicator sections={track.sections} positionMs={player.playback_position_ms} />
        </>
      );
    }

    // Fallback
    return <DeckEmptyState kind="no-player" deckNumber={deckNumber} />;
  }
}
