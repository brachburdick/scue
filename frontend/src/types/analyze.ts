/** Types for the scan & batch analyze flow (FE-4). */

export interface ScannedFile {
  path: string;
  filename: string;
}

export interface ScanResponse {
  path: string;
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
  status: "pending" | "running" | "complete" | "failed";
  total: number;
  completed: number;
  failed: number;
  current_file: string | null;
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
