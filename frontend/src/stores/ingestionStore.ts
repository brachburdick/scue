/** Zustand store for ingestion page state.
 *
 * Receives scan_progress / scan_complete WS messages dispatched by api/ws.ts.
 * Also receives rekordbox_progress WS messages for master.db ingest progress.
 * Independent silo — does not import other stores.
 */

import { create } from "zustand";
import type { HardwareScanStatus } from "../types/ingestion";

/** Real-time progress state for master.db ingest (Phase 1). */
export interface RekordboxIngestProgress {
  phase: "scanning" | "ingesting" | "complete" | "scan_complete" | "ingest_complete" | "cancelled" | "error";
  message: string;
  current?: number;
  total?: number;
  /** Overall phase step (e.g. 2 of 4: "Parsing ANLZ data") */
  step?: number;
  totalSteps?: number;
  stepName?: string;
}

/** Scan result delivered via WS scan_complete event. */
export interface RekordboxScanResult {
  status: string;
  total_tracks: number;
  with_audio: number;
  with_anlz: number;
  matched_to_scue: number;
  sidecars_created: number;
  scan_time_seconds: number;
  matched_tracks: Array<{ fingerprint: string; title: string; artist: string; bpm: number; phrases: number; beats: number }>;
  importable_tracks: Array<{ title: string; artist: string; bpm: number; audio_path: string; phrases: number }>;
}

interface IngestionState {
  /** Real-time hardware scan progress from WS events. */
  hardwareScanProgress: HardwareScanStatus | null;

  /** Whether a hardware scan is currently in progress. */
  hardwareScanInProgress: boolean;

  /** Real-time rekordbox ingest progress from WS events. */
  rekordboxIngest: RekordboxIngestProgress | null;

  /** Scan result delivered via WS (non-blocking scan). */
  rekordboxScanResult: RekordboxScanResult | null;

  /** Ingest result delivered via WS (non-blocking ingest). */
  rekordboxIngestResult: Record<string, unknown> | null;

  /** Set hardware scan progress (from WS scan_progress message). */
  setScanProgress: (status: HardwareScanStatus) => void;

  /** Mark scan complete (from WS scan_complete message). */
  setScanComplete: (status: HardwareScanStatus) => void;

  /** Clear scan state. */
  clearScanProgress: () => void;

  /** Set rekordbox ingest progress (from WS rekordbox_progress message). */
  setRekordboxProgress: (payload: { phase: string; message: string; detail?: Record<string, unknown> }) => void;

  /** Clear rekordbox ingest state. */
  clearRekordboxProgress: () => void;
}

export const useIngestionStore = create<IngestionState>((set) => ({
  hardwareScanProgress: null,
  hardwareScanInProgress: false,
  rekordboxIngest: null,
  rekordboxScanResult: null,
  rekordboxIngestResult: null,

  setScanProgress: (status) =>
    set({ hardwareScanProgress: status, hardwareScanInProgress: true }),

  setScanComplete: (status) =>
    set({ hardwareScanProgress: status, hardwareScanInProgress: false }),

  clearScanProgress: () =>
    set({ hardwareScanProgress: null, hardwareScanInProgress: false }),

  setRekordboxProgress: (payload) => {
    const phase = payload.phase as RekordboxIngestProgress["phase"];
    const update: Partial<IngestionState> = {
      rekordboxIngest: {
        phase,
        message: payload.message,
        current: payload.detail?.current as number | undefined,
        total: payload.detail?.total as number | undefined,
        step: payload.detail?.step as number | undefined,
        totalSteps: payload.detail?.total_steps as number | undefined,
        stepName: payload.detail?.step_name as string | undefined,
      },
    };
    // When scan_complete arrives, store the full scan result
    if (phase === "scan_complete" && payload.detail) {
      update.rekordboxScanResult = payload.detail as unknown as RekordboxScanResult;
    }
    // When ingest_complete arrives, store the ingest result
    if (phase === "ingest_complete" && payload.detail) {
      update.rekordboxIngestResult = payload.detail as Record<string, unknown>;
    }
    set(update);
  },

  clearRekordboxProgress: () =>
    set({ rekordboxIngest: null }),
}));
