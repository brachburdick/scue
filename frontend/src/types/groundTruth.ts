/** Ground truth annotation types for M7 event detection tuning. */

import type { EventType } from "./events";

/** Tracks origin of each annotation for training data and regression detection. */
export type AnnotationSource = "predicted" | "corrected" | "manual";

export interface GroundTruthEvent {
  type: EventType;
  timestamp: number;
  duration?: number;
  /** Origin of this annotation. Optional for backwards compat with legacy files. */
  source?: AnnotationSource;
}

export interface GroundTruthResponse {
  fingerprint: string;
  events: GroundTruthEvent[];
  updated_at: number | null;
}

export interface GroundTruthListItem {
  fingerprint: string;
  event_count: number;
  updated_at: number;
}

export interface GroundTruthListResponse {
  tracks: GroundTruthListItem[];
}

export interface ScoreCardResult {
  precision: number;
  recall: number;
  f1: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
}

export interface ScoreResponse {
  fingerprint: string;
  scores: Record<string, ScoreCardResult>;
  total_detected: number;
  total_ground_truth: number;
}

/** Snap resolution for annotation placement. */
export type SnapResolution = "16th" | "32nd" | "64th" | "off";

/** Placement mode for annotations. */
export type PlacementMode = "point" | "region";
