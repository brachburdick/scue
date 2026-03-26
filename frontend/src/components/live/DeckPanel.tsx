import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { PlayerInfo } from "../../types/bridge";
import type { MusicalEvent } from "../../types/events";
import { usePioneerWaveform, useResolveTrack, useTrackAnalysis, useTrackEvents } from "../../api/tracks";
import { useActiveEvents } from "../../hooks/useActiveEvents";
import { DeckWaveform } from "./DeckWaveform";
import { DeckMetadata } from "./DeckMetadata";
import { DeckEmptyState } from "./DeckEmptyState";
import { LiveEventDisplay } from "../shared/LiveEventDisplay.tsx";
import type { EmptyStateKind } from "./DeckEmptyState";

export interface DeckPanelProps {
  deckNumber: 1 | 2;
  player: PlayerInfo | undefined;
  bridgeOverride: EmptyStateKind | null;
}

export function DeckPanel({ deckNumber, player, bridgeOverride }: DeckPanelProps) {
  const queryClient = useQueryClient();
  const rbId = player?.rekordbox_id ?? null;
  const srcPlayer = player?.track_source_player ?? 0;
  const srcSlot = player?.track_source_slot ?? "";

  const handleRetryResolve = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: ["resolve-track", srcPlayer, srcSlot, rbId],
    });
  }, [queryClient, srcPlayer, srcSlot, rbId]);

  const resolve = useResolveTrack(srcPlayer, srcSlot, rbId && rbId > 0 ? rbId : null);
  const fingerprint = resolve.data?.fingerprint ?? null;
  const analysis = useTrackAnalysis(fingerprint);
  const pioneerWfVersion = player?.pioneer_waveform_version ?? 0;
  const pioneerWf = usePioneerWaveform(deckNumber, pioneerWfVersion);
  const eventsQuery = useTrackEvents(fingerprint);

  // Expand drum patterns for live event display
  const track = analysis.data ?? null;
  const expandedEvents: MusicalEvent[] = useMemo(() => {
    if (!eventsQuery.data || !track) return [];
    const tonal = eventsQuery.data.events ?? [];
    const percussion: MusicalEvent[] = [];
    const beats = (track.beats ?? []) as number[];
    const downbeats = (track.downbeats ?? []) as number[];
    if (beats.length >= 2 && downbeats.length > 0 && eventsQuery.data.drum_patterns) {
      const avgBeatDur = (beats[beats.length - 1] - beats[0]) / (beats.length - 1);
      const sixteenthDur = avgBeatDur / 4;
      for (const pattern of eventsQuery.data.drum_patterns) {
        for (let bar = pattern.bar_start; bar < pattern.bar_end; bar++) {
          if (bar >= downbeats.length) break;
          const barTime = downbeats[bar];
          const localBar = bar - pattern.bar_start;
          const slotOffset = localBar * 16;
          for (let slot = 0; slot < 16; slot++) {
            const absSlot = slotOffset + slot;
            const t = barTime + slot * sixteenthDur;
            if (absSlot < pattern.kick.length && pattern.kick[absSlot])
              percussion.push({ type: "kick", timestamp: t, duration: null, intensity: 0.8, payload: {} });
            if (absSlot < pattern.snare.length && pattern.snare[absSlot])
              percussion.push({ type: "snare", timestamp: t, duration: null, intensity: 0.7, payload: {} });
            if (absSlot < pattern.clap.length && pattern.clap[absSlot])
              percussion.push({ type: "clap", timestamp: t, duration: null, intensity: 0.6, payload: {} });
          }
        }
      }
    }
    return [...tonal, ...percussion].sort((a, b) => a.timestamp - b.timestamp);
  }, [eventsQuery.data, track]);

  // Shared playback context
  const positionSec = player?.playback_position_ms != null
    ? player.playback_position_ms / 1000
    : null;
  const activeState = useActiveEvents(
    positionSec,
    expandedEvents,
    track?.sections ?? [],
    (track?.beats ?? []) as number[],
    (track?.downbeats ?? []) as number[],
  );

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

    // D4: Not found — try Pioneer waveform fallback
    if (resolve.isError || (!resolve.isLoading && !fingerprint)) {
      if (pioneerWf.data) {
        return (
          <>
            <div className="relative">
              <DeckWaveform
                waveform={pioneerWf.data}
                sections={[]}
                duration={pioneerWf.data.duration}
                positionMs={player.playback_position_ms}
                bpm={player.bpm}
              />
              <span className="absolute top-1 right-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-900/70 text-blue-300 border border-blue-700/50">
                Pioneer
              </span>
            </div>
            <DeckMetadata player={player} analysis={null} />
          </>
        );
      }
      return (
        <>
          <DeckEmptyState
            kind="not-found"
            deckNumber={deckNumber}
            rekordboxId={rbId}
            sourcePlayer={srcPlayer}
            sourceSlot={srcSlot}
            player={player}
            onRetry={handleRetryResolve}
          />
          <DeckMetadata player={player} analysis={null} />
        </>
      );
    }

    // D5: Analysis loading
    if (analysis.isLoading) {
      return <DeckEmptyState kind="loading-analysis" deckNumber={deckNumber} />;
    }

    // D7: No SCUE waveform — try Pioneer waveform fallback
    if (track && !track.waveform) {
      if (pioneerWf.data) {
        return (
          <>
            <div className="relative">
              <DeckWaveform
                waveform={pioneerWf.data}
                sections={track.sections}
                duration={track.duration}
                positionMs={player.playback_position_ms}
                bpm={player.bpm}
              />
              <span className="absolute top-1 right-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-900/70 text-blue-300 border border-blue-700/50">
                Pioneer
              </span>
            </div>
            <DeckMetadata player={player} analysis={track} />
            <LiveEventDisplay state={activeState} layout="vertical" className="mt-1" />
          </>
        );
      }
      return (
        <>
          <DeckEmptyState kind="no-waveform" deckNumber={deckNumber} />
          <DeckMetadata player={player} analysis={track} />
          <LiveEventDisplay state={activeState} layout="vertical" className="mt-1" />
        </>
      );
    }

    // D6: Full data (D8 handled by LiveEventDisplay showing "No playback" / section)
    if (track && track.waveform) {
      return (
        <>
          <DeckWaveform
            waveform={track.waveform}
            sections={track.sections}
            duration={track.duration}
            positionMs={player.playback_position_ms}
            bpm={player.bpm}
          />
          <DeckMetadata player={player} analysis={track} />
          <LiveEventDisplay state={activeState} layout="vertical" className="mt-1" />
        </>
      );
    }

    // Fallback
    return <DeckEmptyState kind="no-player" deckNumber={deckNumber} />;
  }
}
