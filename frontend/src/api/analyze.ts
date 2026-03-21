/** API functions and hooks for scan & batch analyze flow (FE-4). */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  ScanResponse,
  BatchAnalyzeResponse,
  JobStatus,
  BrowseResponse,
  FolderContentsResponse,
  LastScanPathResponse,
} from "../types";

export async function scanDirectory(
  path: string,
  recursive = true,
  destinationFolder = "",
): Promise<ScanResponse> {
  return apiFetch<ScanResponse>("/tracks/scan", {
    method: "POST",
    body: JSON.stringify({
      path,
      recursive,
      destination_folder: destinationFolder,
    }),
  });
}

export async function startBatchAnalysis(
  paths: string[],
  skipWaveform = false,
  scanRoot = "",
  destinationFolder = "",
): Promise<BatchAnalyzeResponse> {
  return apiFetch<BatchAnalyzeResponse>("/tracks/analyze-batch", {
    method: "POST",
    body: JSON.stringify({
      paths,
      skip_waveform: skipWaveform,
      scan_root: scanRoot,
      destination_folder: destinationFolder,
    }),
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
      if (status === "complete" || status === "complete_with_errors") return false;
      return 1000;
    },
  });
}

export async function getLastScanPath(): Promise<LastScanPathResponse> {
  return apiFetch<LastScanPathResponse>("/tracks/settings/last-scan-path");
}

export function useFolderContents(parent: string, enabled = true) {
  return useQuery<FolderContentsResponse>({
    queryKey: ["folder-contents", parent],
    queryFn: () =>
      apiFetch<FolderContentsResponse>(
        `/tracks/folders?parent=${encodeURIComponent(parent)}`,
      ),
    enabled,
  });
}

export async function createFolder(path: string): Promise<{ path: string }> {
  return apiFetch<{ path: string }>("/tracks/folders", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export async function moveTrackToFolder(
  fingerprint: string,
  folder: string,
): Promise<{ fingerprint: string; folder: string }> {
  return apiFetch<{ fingerprint: string; folder: string }>(
    `/tracks/${fingerprint}/folder`,
    {
      method: "PATCH",
      body: JSON.stringify({ folder }),
    },
  );
}
