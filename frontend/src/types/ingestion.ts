/** Types for the Ingestion page — three-source track library with scanner controls.
 *
 * These types mirror the actual backend response shapes documented in
 * docs/BRIDGE_CONTRACT.md §4. Do NOT change these without verifying the BE shape.
 */

// ─── Local Library Scanner ────────────────────────────────────────────

export interface LibraryDetectResponse {
  path: string;
  dat_count: number;
}

export interface LibraryScanParams {
  path?: string | null;
  force_rescan?: boolean;
}

/** A matched track from POST /api/local-library/scan → matched_tracks[]. */
export interface LibraryMatchedTrack {
  title: string;
  file_path: string;
  fingerprint: string;
  match_method: string;
}

/** An unmatched track from POST /api/local-library/scan → unmatched_tracks[]. */
export interface LibraryUnmatchedTrack {
  title: string;
  file_path: string;
}

/** Response from POST /api/local-library/scan and GET /status (when scan exists). */
export interface LibraryScanResult {
  status: "complete";
  source: string;
  total_tracks: number;
  matched: number;
  unmatched: number;
  already_linked: number;
  scan_timestamp: number;
  matched_tracks: LibraryMatchedTrack[];
  unmatched_tracks: LibraryUnmatchedTrack[];
}

/** Sentinel from GET /api/local-library/status before first scan. */
export interface LibraryNoScanStatus {
  status: "no_scan";
  message: string;
}

/** Discriminated union for GET /api/local-library/status. */
export type LibraryScanStatus = LibraryScanResult | LibraryNoScanStatus;

// ─── Hardware Scanner ─────────────────────────────────────────────────

export interface UsbTrack {
  rekordbox_id: number;
  title: string;
  artist: string;
}

export interface UsbBrowseResponse {
  player: number;
  slot: string;
  track_count: number;
  tracks: UsbTrack[];
}

export interface UsbMenuItem {
  id: number;
  name: string;
  is_folder: boolean;
}

export interface UsbMenuResponse {
  items: UsbMenuItem[];
}

export interface UsbFolderResponse {
  items: UsbMenuItem[];
  tracks: UsbTrack[];
}

export interface StartHardwareScanParams {
  player: number;
  slot: string;
  target_players?: number[];
  track_ids?: number[];
  force_rescan?: boolean;
}

export interface DeckProgress {
  status: string;
  current_track: string | null;
  scanned: number;
  total: number;
}

export interface HardwareScanStatus {
  status: "idle" | "browsing" | "scanning" | "stopping" | "completed" | "failed";
  total: number;
  scanned: number;
  skipped: number;
  errors: number;
  deck_progress: Record<number, DeckProgress>;
}

export interface ScannedHistoryTrack {
  rekordbox_id: number;
  title: string;
  artist: string;
  fingerprint: string;
  scanned_at: number;
}

export interface ScanHistoryResponse {
  tracks: ScannedHistoryTrack[];
}

// ─── WebSocket Events ─────────────────────────────────────────────────

export interface WSScanProgress {
  type: "scan_progress";
  payload: HardwareScanStatus;
}

export interface WSScanComplete {
  type: "scan_complete";
  payload: HardwareScanStatus;
}

// ─── Track Library (unified view) ─────────────────────────────────────

export type IngestionSource = "library" | "hardware" | "audio";

export type IngestionTab = "library" | "hardware" | "audio";
