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
}

const Spinner = () => (
  <span className="animate-spin h-4 w-4 border-2 border-gray-500 border-t-transparent rounded-full inline-block" />
);

export function DeckEmptyState({ kind, deckNumber, rekordboxId, sourcePlayer, sourceSlot }: DeckEmptyStateProps) {
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
      content = `Unknown track (rekordbox_id: ${rekordboxId}, source: Player ${sourcePlayer} ${sourceSlot}) — analyze this track to see waveform`;
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
