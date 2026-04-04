/** WebSocket message types for real-time FE/BE communication. */

import type { BridgeState } from "./bridge";
import type { HardwareScanStatus } from "./ingestion";
import type { ArrangementFormula } from "./strata";

export interface WSBridgeStatus {
  type: "bridge_status";
  payload: BridgeState;
}

export interface WSPioneerStatus {
  type: "pioneer_status";
  payload: {
    is_receiving: boolean;
    bridge_connected: boolean;
    last_message_age_ms: number;
  };
}

export interface WSStrataLive {
  type: "strata_live";
  payload: {
    player_number: number;
    formula: ArrangementFormula;
  };
}

export interface WSScanProgress {
  type: "scan_progress";
  payload: HardwareScanStatus;
}

export interface WSScanComplete {
  type: "scan_complete";
  payload: HardwareScanStatus;
}

export interface WSMediaChange {
  type: "media_change";
  payload: {
    player_number: number;
    slot: string;
    action: "mounted" | "unmounted";
  };
}

export interface WSRekordboxProgress {
  type: "rekordbox_progress";
  payload: {
    phase: "scanning" | "ingesting" | "complete" | "scan_complete" | "ingest_complete" | "cancelled" | "error";
    message: string;
    detail?: {
      current?: number;
      total?: number;
      [key: string]: unknown;
    };
  };
}

export interface WSAnalysisProgress {
  type: "analysis_progress";
  payload: {
    kind: "batch" | "single";
    batch_id?: string;
    job_id?: string;
    status: "running" | "complete" | "failed" | "cancelled";
    tier: string;
    completed: number;
    failed: number;
    total: number;
    current_track?: {
      fingerprint: string;
      title: string;
      step: number;
      step_name: string;
      total_steps: number;
    };
  };
}

export type WSMessage =
  | WSBridgeStatus
  | WSPioneerStatus
  | WSStrataLive
  | WSScanProgress
  | WSScanComplete
  | WSMediaChange
  | WSRekordboxProgress
  | WSAnalysisProgress;
