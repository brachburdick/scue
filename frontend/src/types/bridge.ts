/** Bridge & network types — mirrors Python dataclasses from scue/network/models.py */

export type BridgeStatus =
  | "stopped"
  | "starting"
  | "running"
  | "crashed"
  | "no_jre"
  | "no_jar"
  | "fallback"
  | "waiting_for_hardware"
  | "not_initialized";

export interface InterfaceAddress {
  address: string;
  netmask: string;
  family: "ipv4" | "ipv6";
  is_link_local: boolean;
}

export interface NetworkInterface {
  name: string;
  display_name: string;
  addresses: InterfaceAddress[];
  is_up: boolean;
  is_loopback: boolean;
  has_link_local: boolean;
  type: "ethernet" | "wifi" | "vpn" | "virtual" | "other";
  score: number;
}

export interface InterfaceListResponse {
  interfaces: NetworkInterface[];
  configured_interface: string | null;
  recommended_interface: string | null;
}

export interface RouteStatusResponse {
  platform: string;
  route_applicable: boolean;
  current_interface: string | null;
  expected_interface: string | null;
  correct: boolean;
  fix_available: boolean;
  sudoers_installed: boolean;
}

export interface RouteFixResponse {
  success: boolean;
  previous_interface: string | null;
  new_interface: string;
  error: string | null;
}

export interface RouteSetupStatus {
  sudoers_installed: boolean;
  launchd_installed: boolean;
  setup_command: string;
}

export interface DeviceInfo {
  device_name: string;
  device_number: number;
  device_type: "cdj" | "djm" | "rekordbox";
  uses_dlp: boolean;
}

export interface PlayerInfo {
  bpm: number;
  pitch: number;
  playback_state: string;
  is_on_air: boolean;
  rekordbox_id: number;
  beat_within_bar: number;
  track_type: string;
  playback_position_ms: number | null;
  track_source_player: number;
  track_source_slot: string;
}

export interface BridgeState {
  status: BridgeStatus;
  port: number;
  network_interface: string | null;
  jar_path: string;
  jar_exists: boolean;
  jre_available: boolean;
  restart_count: number;
  restart_attempt: number;
  next_retry_in_s: number | null;
  route_correct: boolean | null;
  route_warning: string | null;
  devices: Record<string, DeviceInfo>;
  players: Record<string, PlayerInfo>;
}
