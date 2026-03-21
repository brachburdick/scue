/** Types for the scan & batch analyze flow (FE-4). */

export interface ScannedFile {
  path: string;
  filename: string;
}

export interface ScanResponse {
  path: string;
  scan_root: string;
  total_files: number;
  already_analyzed: number;
  new_files: ScannedFile[];
}

export interface BatchAnalyzeResponse {
  job_id: string;
}

export interface JobFileResult {
  path: string;
  filename: string;
  fingerprint: string;
  status: "pending" | "done" | "error";
  error?: string;
}

export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "complete" | "complete_with_errors" | "failed";
  total: number;
  completed: number;
  failed: number;
  current_file: string | null;
  current_step: number;
  current_step_name: string;
  total_steps: number;
  results: JobFileResult[];
}

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface BrowseResponse {
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}

export interface FolderInfo {
  name: string;
  path: string;
  track_count: number;
}

export interface FolderContentsResponse {
  parent: string;
  folders: FolderInfo[];
  tracks: import("./track").TrackSummary[];
  track_count: number;
}

export interface LastScanPathResponse {
  path: string | null;
  recent: string[];
}
