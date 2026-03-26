import { useState, useMemo, useEffect, useRef } from "react";
import { useBridgeStore } from "../../stores/bridgeStore";
import { useIngestionStore } from "../../stores/ingestionStore";
import { useStartHardwareScan, useStopHardwareScan, useScanHistory } from "../../api/ingestion";
import { UsbBrowser } from "./UsbBrowser";
import { ScanProgressPanel } from "./ScanProgressPanel";
import type { DeviceInfo } from "../../types/bridge";

export function HardwareTab() {
  const status = useBridgeStore((s) => s.status);
  const devices = useBridgeStore((s) => s.devices);
  const players = useBridgeStore((s) => s.players);
  const isStartingUp = useBridgeStore((s) => s.isStartingUp);
  const scanProgress = useIngestionStore((s) => s.hardwareScanProgress);
  const scanInProgress = useIngestionStore((s) => s.hardwareScanInProgress);

  const [selectedTrackIds, setSelectedTrackIds] = useState<Set<number>>(new Set());
  const [targetDecks, setTargetDecks] = useState<Set<number>>(new Set());
  const [forceRescan, setForceRescan] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<number | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<"usb" | "sd">("usb");

  const startScan = useStartHardwareScan();
  const stopScan = useStopHardwareScan();
  const bridgeRunning = !isStartingUp && status === "running";
  const { data: history } = useScanHistory(bridgeRunning);

  const cdjDevices = useMemo(() => {
    const allCdj = Object.values(devices).filter(
      (d: DeviceInfo) => d.device_type === "cdj",
    );
    // Deduplicate by device_number — all-in-one units (XDJ-AZ) announce as
    // both player devices and a mixer/controller sharing a player's number.
    const seen = new Set<number>();
    return allCdj.filter((d) => {
      if (seen.has(d.device_number)) return false;
      seen.add(d.device_number);
      return true;
    });
  }, [devices]);

  // Auto-select first player if none selected
  const activePlayer = selectedPlayer ?? (cdjDevices.length > 0 ? cdjDevices[0].device_number : null);

  const scannedIds = useMemo(() => {
    return new Set((history?.tracks ?? []).map((t) => t.rekordbox_id));
  }, [history]);

  // Initialize target decks to all CDJs (deduplicated)
  const availableDecks = useMemo(() => cdjDevices.map((d) => d.device_number), [cdjDevices]);

  const effectiveTargetDecks = targetDecks.size > 0 ? targetDecks : new Set(availableDecks);

  // Clear selections when scan completes
  const prevScanStatus = useRef(scanProgress?.status);
  useEffect(() => {
    const curr = scanProgress?.status;
    if (prevScanStatus.current && prevScanStatus.current !== curr &&
        (curr === "completed" || curr === "failed")) {
      setSelectedTrackIds(new Set());
    }
    prevScanStatus.current = curr;
  }, [scanProgress?.status]);

  if (isStartingUp) {
    return <div className="text-gray-500 text-sm animate-pulse">Connecting...</div>;
  }

  if (status !== "running") {
    return (
      <div className="rounded border border-gray-800 bg-gray-900/50 p-4">
        <p className="text-gray-400 text-sm">Bridge is not connected.</p>
        <p className="text-gray-600 text-xs mt-1">
          Start the bridge and connect CDJ hardware to use the hardware scanner.
        </p>
      </div>
    );
  }

  if (cdjDevices.length === 0) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900/50 p-4">
        <p className="text-gray-400 text-sm">No CDJ devices detected.</p>
        <p className="text-gray-600 text-xs mt-1">
          Connect CDJ/XDJ players to the network.
        </p>
      </div>
    );
  }

  const handleStartScan = (scanAll: boolean) => {
    if (!activePlayer) return;
    startScan.mutate({
      player: activePlayer,
      slot: selectedSlot,
      target_players: [...effectiveTargetDecks],
      track_ids: scanAll ? undefined : [...selectedTrackIds],
      force_rescan: forceRescan,
    });
  };

  const handleStopScan = () => {
    stopScan.mutate();
  };

  const toggleDeck = (deck: number) => {
    setTargetDecks((prev) => {
      const next = new Set(prev.size > 0 ? prev : availableDecks);
      if (next.has(deck)) next.delete(deck);
      else next.add(deck);
      return next;
    });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Left: USB Browser */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-gray-300">USB Browser</h3>
          {cdjDevices.length > 1 && (
            <select
              value={activePlayer ?? ""}
              onChange={(e) => {
                setSelectedPlayer(Number(e.target.value));
                setSelectedTrackIds(new Set());
              }}
              className="text-xs rounded border border-gray-700 bg-gray-800 text-gray-300 px-2 py-1"
            >
              {cdjDevices.map((d) => (
                <option key={d.device_number} value={d.device_number}>
                  Player {d.device_number} ({d.device_name})
                </option>
              ))}
            </select>
          )}
          <select
            value={selectedSlot}
            onChange={(e) => {
              setSelectedSlot(e.target.value as "usb" | "sd");
              setSelectedTrackIds(new Set());
            }}
            className="text-xs rounded border border-gray-700 bg-gray-800 text-gray-300 px-2 py-1"
          >
            <option value="usb">USB</option>
            <option value="sd">SD</option>
          </select>
        </div>

        {activePlayer !== null && (
          <UsbBrowser
            player={activePlayer}
            slot={selectedSlot}
            scannedIds={scannedIds}
            selectedIds={selectedTrackIds}
            onSelectionChange={setSelectedTrackIds}
          />
        )}
      </div>

      {/* Right: Scan Controls */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-300">Scan Controls</h3>

        {/* Deck picker */}
        <div className="space-y-2">
          <p className="text-xs text-gray-500">Target decks for parallel scanning:</p>
          <div className="flex items-center gap-3">
            {availableDecks.map((deck) => (
              <label key={deck} className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={effectiveTargetDecks.has(deck)}
                  onChange={() => toggleDeck(deck)}
                  className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
                />
                Deck {deck}
              </label>
            ))}
          </div>
        </div>

        {/* Force rescan */}
        <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={forceRescan}
            onChange={(e) => setForceRescan(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
          />
          Force Rescan
        </label>

        {/* Scan buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleStartScan(false)}
            disabled={scanInProgress || selectedTrackIds.size === 0}
            className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors"
          >
            Scan Selected ({selectedTrackIds.size})
          </button>
          <button
            onClick={() => handleStartScan(true)}
            disabled={scanInProgress}
            className="px-4 py-2 text-sm font-medium rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors"
          >
            Scan All
          </button>
        </div>

        {startScan.isError && (
          <p className="text-red-400 text-xs">Failed to start scan: {startScan.error.message}</p>
        )}

        {/* Progress panel */}
        {scanProgress && (
          <ScanProgressPanel
            progress={scanProgress}
            onStop={handleStopScan}
            onDismiss={() => {
              useIngestionStore.getState().clearScanProgress();
              setSelectedTrackIds(new Set());
            }}
            isStopping={stopScan.isPending}
          />
        )}
      </div>
    </div>
  );
}
