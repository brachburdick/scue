import type { PlayerInfo } from "../../types";

export function PlayerCard({
  playerNumber,
  player,
}: {
  playerNumber: string;
  player: PlayerInfo;
}) {
  const isPlaying = player.playback_state === "playing";

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold text-white">P{playerNumber}</span>
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            isPlaying
              ? "bg-green-900/50 text-green-400"
              : "bg-gray-700 text-gray-400"
          }`}
        >
          {player.playback_state}
        </span>
        {player.is_on_air && (
          <span className="rounded bg-red-900/50 px-2 py-0.5 text-xs text-red-400">
            ON AIR
          </span>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span>{player.bpm.toFixed(1)} BPM</span>
        <span>Beat {player.beat_within_bar}/4</span>
        {player.pitch !== 0 && (
          <span className="text-gray-500">
            {player.pitch > 0 ? "+" : ""}
            {player.pitch.toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  );
}
