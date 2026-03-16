/** API functions and hooks for scan & batch analyze flow (FE-4). */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ScanResponse, BatchAnalyzeResponse, JobStatus, BrowseResponse } from "../types";

export async function scanDirectory(path: string): Promise<ScanResponse> {
  return apiFetch<ScanResponse>("/tracks/scan", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export async function startBatchAnalysis(
  paths: string[],
  skipWaveform = false,
): Promise<BatchAnalyzeResponse> {
  return apiFetch<BatchAnalyzeResponse>("/tracks/analyze-batch", {
    method: "POST",
    body: JSON.stringify({ paths, skip_waveform: skipWaveform }),
  });
}

export async function browseFilesystem(path?: string): Promise<BrowseResponse> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<BrowseResponse>(`/filesystem/browse${qs}`, { method: "GET" });
}

export function useJobStatus(jobId: string | null) {
  return useQuery<JobStatus>({
    queryKey: ["job", jobId],
    queryFn: () => apiFetch<JobStatus>(`/tracks/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "complete" || status === "failed") return false;
      return 1000;
    },
  });
}
