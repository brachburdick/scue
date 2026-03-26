import type { PlayerInfo } from "../../types";
import { useBridgeStore } from "../../stores/bridgeStore";
import { PlayerCard } from "./PlayerCard";

/** Small inline spinner for S4 (starting) state. */
function Spinner() {
  return (
    <svg
      className="inline-block w-4 h-4 animate-spin text-gray-500 ml-1"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

/** Pulsing dot indicator for S6 (recovering) state. */
function PulsingIndicator() {
  return (
    <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse ml-1" />
  );
}

export function PlayerList({
  players,
}: {
  players: Record<string, PlayerInfo>;
}) {
  const entries = Object.entries(players);
  const status = useBridgeStore((s) => s.status);
  const wsConnected = useBridgeStore((s) => s.wsConnected);

  const isRecovering = useBridgeStore((s) => s.isRecovering);
  const isHwDisconnected = useBridgeStore((s) => s.isHwDisconnected);

  if (entries.length > 0) {
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

  // --- Empty state: priority order per spec ---

  // S7: WS disconnected (highest priority)
  if (!wsConnected) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">Backend unreachable.</p>
      </div>
    );
  }

  // S3: crashed
  if (status === "crashed") {
    return (
      <div className="rounded-lg border border-dashed border-red-900/50 px-4 py-6 text-center">
        <p className="text-sm text-red-400/80">
          Bridge crashed. Player data will resume after restart.
        </p>
      </div>
    );
  }

  // S4: starting
  if (status === "starting") {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">
          Bridge starting…
          <Spinner />
        </p>
      </div>
    );
  }

  // S5: waiting_for_hardware
  if (status === "waiting_for_hardware") {
    return (
      <div className="rounded-lg border border-dashed border-blue-900/50 px-4 py-6 text-center">
        <p className="text-sm text-blue-400/80">Waiting for hardware.</p>
      </div>
    );
  }

  // S8: hardware disconnected — running but no devices/traffic for 8s+
  if (isHwDisconnected) {
    return (
      <div className="rounded-lg border border-dashed border-orange-900/50 px-4 py-6 text-center">
        <p className="text-sm text-orange-400/80">
          Hardware disconnected. Reconnect a CDJ or DJM.
        </p>
      </div>
    );
  }

  // S6: running (recovering) — uses isRecovering from TASK-006a
  if (isRecovering) {
    return (
      <div className="rounded-lg border border-dashed border-green-900/50 px-4 py-6 text-center">
        <p className="text-sm text-green-400/80">
          Waiting for player data…
          <PulsingIndicator />
        </p>
      </div>
    );
  }

  // Default: no active players
  return (
    <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
      <p className="text-sm text-gray-500">No active players.</p>
    </div>
  );
}
