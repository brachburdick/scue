import type { PlayerInfo } from "../../types";
import { PlayerCard } from "./PlayerCard";

export function PlayerList({
  players,
}: {
  players: Record<string, PlayerInfo>;
}) {
  const entries = Object.entries(players);

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">No active players.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">
        Players ({entries.length})
      </h3>
      {entries.map(([pn, player]) => (
        <PlayerCard key={pn} playerNumber={pn} player={player} />
      ))}
    </div>
  );
}
