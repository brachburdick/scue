/** Zustand store for ingestion page state.
 *
 * Receives scan_progress / scan_complete WS messages dispatched by api/ws.ts.
 * Independent silo — does not import other stores.
 */

import { create } from "zustand";
import type { HardwareScanStatus } from "../types/ingestion";

interface IngestionState {
  /** Real-time hardware scan progress from WS events. */
  hardwareScanProgress: HardwareScanStatus | null;

  /** Whether a hardware scan is currently in progress. */
  hardwareScanInProgress: boolean;

  /** Set hardware scan progress (from WS scan_progress message). */
  setScanProgress: (status: HardwareScanStatus) => void;

  /** Mark scan complete (from WS scan_complete message). */
  setScanComplete: (status: HardwareScanStatus) => void;

  /** Clear scan state. */
  clearScanProgress: () => void;
}

export const useIngestionStore = create<IngestionState>((set) => ({
  hardwareScanProgress: null,
  hardwareScanInProgress: false,

  setScanProgress: (status) =>
    set({ hardwareScanProgress: status, hardwareScanInProgress: true }),

  setScanComplete: (status) =>
    set({ hardwareScanProgress: status, hardwareScanInProgress: false }),

  clearScanProgress: () =>
    set({ hardwareScanProgress: null, hardwareScanInProgress: false }),
}));
