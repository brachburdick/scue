/** WebSocket message types for real-time FE/BE communication. */

import type { BridgeState } from "./bridge";

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

export type WSMessage = WSBridgeStatus | WSPioneerStatus;
