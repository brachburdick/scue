/** Track types — mirrors Python dataclasses from scue/layer1/models.py */

export type SectionLabel =
  | "intro"
  | "verse"
  | "build"
  | "drop"
  | "breakdown"
  | "fakeout"
  | "outro";

export type Mood =
  | "dark"
  | "euphoric"
  | "melancholic"
  | "aggressive"
  | "neutral";

export type DataSource = "analysis" | "pioneer_enriched";

export interface Section {
  label: SectionLabel;
  start: number;
  end: number;
  confidence: number;
  bar_count: number;
  expected_bar_count: number;
  irregular_phrase: boolean;
  fakeout: boolean;
  original_label: string;
  source: DataSource;
}

export interface TrackFeatures {
  energy_curve: number[];
  mood: Mood;
  danceability: number;
  key: string;
  key_confidence: number;
  key_source: DataSource;
}

export interface RGBWaveform {
  sample_rate: number;
  duration: number;
  low: number[];
  mid: number[];
  high: number[];
}

export interface MusicalEvent {
  type: string;
  timestamp: number;
  duration: number | null;
  intensity: number;
  payload: Record<string, unknown>;
}

/** Flattened track metadata returned by GET /api/tracks (from SQLite cache). */
export interface TrackSummary {
  fingerprint: string;
  version: number;
  source: DataSource;
  audio_path: string;
  title: string;
  artist: string;
  bpm: number;
  duration: number;
  section_count: number;
  mood: string;
  key_name: string;
  created_at: number;
  folder: string;
  has_quick?: boolean;
  has_standard?: boolean;
  has_deep?: boolean;
  has_live?: boolean;
  has_live_offline?: boolean;
}

/** Full track analysis returned by GET /api/tracks/{fingerprint} (from JSON). */
export interface TrackAnalysis {
  fingerprint: string;
  audio_path: string;
  title: string;
  artist: string;
  bpm: number;
  beats: number[];
  downbeats: number[];
  beatgrid_source: DataSource;
  sections: Section[];
  events: MusicalEvent[];
  features: TrackFeatures;
  waveform: RGBWaveform | null;
  version: number;
  source: DataSource;
  created_at: number;
  duration: number;
  pioneer_bpm: number | null;
  pioneer_key: string | null;
  pioneer_beatgrid: number[] | null;
  rekordbox_id: number | null;
  enrichment_timestamp: number | null;
}

/** Response shape from GET /api/tracks */
export interface TrackListResponse {
  tracks: TrackSummary[];
  total: number;
}
