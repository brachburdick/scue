/** Strata arrangement engine types — mirrors Python strata/models.py. */

export type StemType = "drums" | "bass" | "vocals" | "other";
export type LayerRole = "rhythm" | "bassline" | "lead" | "pad" | "arpeggio" | "fx" | "vocal" | "unknown";
export type PatternType = "drum_groove" | "arpeggio" | "bassline" | "chord_prog" | "vocal_phrase" | "perc_fill" | "custom";
export type TransitionType = "layer_enter" | "layer_exit" | "pattern_change" | "fill" | "energy_shift" | "breakdown" | "drop_impact";
export type StrataTier = "quick" | "standard" | "deep" | "live" | "live_offline";
export type AnalysisSource = "analysis" | "pioneer_enriched" | "pioneer_reanalyzed" | "pioneer_live";

export interface ActivitySpan {
  start: number;
  end: number;
  bar_start: number;
  bar_end: number;
  energy: number;
  confidence: number;
}

export interface AtomicEvent {
  type: string;
  timestamp: number;
  duration: number | null;
  intensity: number;
  stem: StemType | null;
  pitch: string | null;
  beat_position: number | null;
  bar_index: number | null;
  confidence: number;
  source: string;
  payload: Record<string, unknown>;
}

export interface PatternTemplate {
  events: AtomicEvent[];
  duration_bars: number;
  duration_seconds: number;
  signature: string;
}

export interface PatternInstance {
  bar_start: number;
  bar_end: number;
  start: number;
  end: number;
  variation: "exact" | "minor" | "major" | "fill";
  variation_description: string;
  confidence: number;
}

export interface Pattern {
  id: string;
  name: string;
  pattern_type: PatternType;
  stem: StemType | null;
  template: PatternTemplate;
  instances: PatternInstance[];
  tags: string[];
}

export interface ArrangementTransition {
  type: TransitionType;
  timestamp: number;
  bar_index: number;
  section_label: string;
  layers_affected: string[];
  patterns_affected: string[];
  energy_delta: number;
  description: string;
  confidence: number;
}

export interface SectionArrangement {
  section_label: string;
  section_start: number;
  section_end: number;
  active_layers: string[];
  active_patterns: string[];
  transitions: ArrangementTransition[];
  energy_level: number;
  energy_trend: "rising" | "falling" | "stable" | "peak" | "valley";
  layer_count: number;
}

export interface StemWaveform {
  sample_rate: number;
  duration: number;
  low: number[];
  mid: number[];
  high: number[];
}

export interface StemAnalysis {
  stem_type: StemType;
  audio_path: string | null;
  layer_role: LayerRole;
  activity: ActivitySpan[];
  events: AtomicEvent[];
  patterns: Pattern[];
  energy_curve: number[];
  waveform?: StemWaveform | null;
}

export interface ArrangementFormula {
  fingerprint: string;
  version: number;
  stems: StemAnalysis[];
  patterns: Pattern[];
  sections: SectionArrangement[];
  transitions: ArrangementTransition[];
  total_layers: number;
  total_patterns: number;
  arrangement_complexity: number;
  energy_narrative: string;
  pipeline_tier: StrataTier;
  analysis_source: AnalysisSource;
  stem_separation_model: string;
  compute_time_seconds: number;
  created_at: number;
}

/** API response: all tiers for a track (nested: tier → source → formula). */
export interface StrataAllTiersResponse {
  fingerprint: string;
  tiers: Partial<Record<StrataTier, Partial<Record<AnalysisSource, ArrangementFormula>>>>;
  available_tiers: StrataTier[];
}

/** API response: single tier + source. */
export interface StrataTierResponse {
  fingerprint: string;
  tier: StrataTier;
  source: AnalysisSource;
  formula: ArrangementFormula;
}

/** API response: list of tracks with strata data. */
export interface StrataListResponse {
  tracks: Array<{
    fingerprint: string;
    tiers: Partial<Record<StrataTier, AnalysisSource[]>>;
  }>;
}

/** API response: track analysis versions. */
export interface TrackVersionInfo {
  version: number;
  source: string;
  beatgrid_source: string;
  n_sections: number;
  n_events: number;
  n_drum_patterns: number;
  bpm: number;
  created_at: number;
}

export interface TrackVersionsResponse {
  fingerprint: string;
  versions: TrackVersionInfo[];
}

/** API response: reanalyze trigger. */
export interface ReanalyzeResponse {
  fingerprint: string;
  status: "started" | "already_exists";
  version?: number;
  source?: string;
  message?: string;
}

/** API response: strata analyze trigger. */
export interface AnalyzeStrataResult {
  fingerprint: string;
  completed_tiers?: string[];
  requested_tiers?: string[];
  analysis_source?: string;
  status: string;
  message?: string;
  job_id?: string;
}

/** Strata job status (for polling standard/deep tier progress). */
export interface StrataJobStatus {
  job_id: string;
  fingerprint: string;
  tier: StrataTier;
  status: "pending" | "running" | "complete" | "failed";
  current_step: number;
  current_step_name: string;
  total_steps: number;
  error: string | null;
}

/** Strata batch job status (for multi-track analysis). */
export interface StrataBatchStatus {
  batch_id: string;
  jobs: StrataJobStatus[];
  status: "pending" | "running" | "complete" | "failed";
  completed: number;
  failed: number;
  total: number;
}
