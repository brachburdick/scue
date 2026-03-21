import type { PlayerInfo } from "../../types/bridge";

export type EmptyStateKind =
  | "no-player"
  | "no-track"
  | "resolving"
  | "not-found"
  | "loading-analysis"
  | "no-waveform"
  | "bridge-crashed"
  | "bridge-starting"
  | "waiting-hardware"
  | "ws-disconnected";

export interface DeckEmptyStateProps {
  kind: EmptyStateKind;
  deckNumber: number;
  rekordboxId?: number;
  sourcePlayer?: number;
  sourceSlot?: string;
  /** Full player data for diagnostic display on not-found state */
  player?: PlayerInfo;
  /** Retry resolution callback */
  onRetry?: () => void;
}

const Spinner = () => (
  <span className="animate-spin h-4 w-4 border-2 border-gray-500 border-t-transparent rounded-full inline-block" />
);

function BridgeDiagnostics({ player, rekordboxId, sourcePlayer, sourceSlot, onRetry }: {
  player?: PlayerInfo;
  rekordboxId?: number;
  sourcePlayer?: number;
  sourceSlot?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="w-full max-w-lg">
      <div className="text-gray-500 text-sm mb-3">
        Unknown track — scan your USB on the Tracks page to link tracks
      </div>

      {/* Bridge data table */}
      <div className="bg-gray-900/80 border border-gray-800 rounded px-3 py-2 text-left">
        <div className="text-[10px] uppercase tracking-wider text-gray-600 mb-1.5">Bridge Data</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-xs">
          <span className="text-gray-600">rekordbox_id</span>
          <span className="text-gray-300">{rekordboxId ?? "—"}</span>
          <span className="text-gray-600">source_player</span>
          <span className="text-gray-300">{sourcePlayer ?? "—"}</span>
          <span className="text-gray-600">source_slot</span>
          <span className="text-gray-300">{sourceSlot ?? "—"}</span>
          {player && (
            <>
              <span className="text-gray-600">bpm</span>
              <span className="text-gray-300">{player.bpm.toFixed(2)}</span>
              <span className="text-gray-600">pitch</span>
              <span className="text-gray-300">{player.pitch.toFixed(1)}%</span>
              <span className="text-gray-600">state</span>
              <span className="text-gray-300">{player.playback_state}</span>
              <span className="text-gray-600">beat</span>
              <span className="text-gray-300">{player.beat_within_bar}/4</span>
              <span className="text-gray-600">track_type</span>
              <span className="text-gray-300">{player.track_type || "—"}</span>
            </>
          )}
        </div>
      </div>

      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 text-xs text-gray-400 hover:text-gray-200 underline underline-offset-2"
        >
          Retry resolution
        </button>
      )}
    </div>
  );
}

export function DeckEmptyState({ kind, deckNumber, rekordboxId, sourcePlayer, sourceSlot, player, onRetry }: DeckEmptyStateProps) {
  let content: React.ReactNode;

  switch (kind) {
    case "ws-disconnected":
      content = "Backend unreachable";
      break;
    case "bridge-crashed":
      content = "Bridge crashed. Deck data will resume after restart.";
      break;
    case "bridge-starting":
      content = <span className="animate-pulse">Bridge starting...</span>;
      break;
    case "waiting-hardware":
      content = "Waiting for Pioneer hardware...";
      break;
    case "no-player":
      content = `Waiting for Deck ${deckNumber} data...`;
      break;
    case "no-track":
      content = `No track loaded on Deck ${deckNumber}`;
      break;
    case "resolving":
      content = (
        <span className="flex items-center gap-2">
          <Spinner /> Resolving track...
        </span>
      );
      break;
    case "not-found":
      content = (
        <BridgeDiagnostics
          player={player}
          rekordboxId={rekordboxId}
          sourcePlayer={sourcePlayer}
          sourceSlot={sourceSlot}
          onRetry={onRetry}
        />
      );
      break;
    case "loading-analysis":
      content = (
        <div className="w-full flex flex-col items-center gap-2">
          <div className="w-full h-32 animate-pulse bg-gray-800 rounded" />
          <span className="text-gray-500 text-sm">Loading analysis...</span>
        </div>
      );
      break;
    case "no-waveform":
      content = "No waveform data — re-analyze with waveform enabled";
      break;
  }

  return (
    <div className="min-h-[120px] flex items-center justify-center text-gray-500 text-sm px-4 text-center">
      {content}
    </div>
  );
}
