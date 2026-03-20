import { useBridgeStore } from "../stores/bridgeStore";
import { DeckPanel } from "../components/live/DeckPanel";
import type { EmptyStateKind } from "../components/live/DeckEmptyState";

function getBridgeOverride(
  wsConnected: boolean,
  status: string,
): EmptyStateKind | null {
  if (!wsConnected) return "ws-disconnected";
  if (status === "crashed") return "bridge-crashed";
  if (status === "starting") return "bridge-starting";
  if (status === "waiting_for_hardware") return "waiting-hardware";
  return null;
}

export function LiveDeckMonitorPage() {
  const wsConnected = useBridgeStore((s) => s.wsConnected);
  const status = useBridgeStore((s) => s.status);
  const players = useBridgeStore((s) => s.players);

  const bridgeOverride = getBridgeOverride(wsConnected, status);
  const player1 = players["1"];
  const player2 = players["2"];

  return (
    <div className="flex flex-col gap-4 h-full">
      <DeckPanel deckNumber={1} player={player1} bridgeOverride={bridgeOverride} />
      <DeckPanel deckNumber={2} player={player2} bridgeOverride={bridgeOverride} />
    </div>
  );
}
