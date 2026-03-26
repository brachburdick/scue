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

export type WSMessage =
  | WSBridgeStatus
  | WSPioneerStatus
  | WSStrataLive
  | WSScanProgress
  | WSScanComplete;
