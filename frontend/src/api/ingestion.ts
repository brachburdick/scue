/** TanStack Query hooks for /api/local-library and /api/scanner endpoints. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { useIngestionStore } from "../stores/ingestionStore";
import type {
  LibraryDetectResponse,
  LibraryScanParams,
  LibraryScanResult,
  LibraryScanStatus,
  UsbBrowseResponse,
  UsbMenuResponse,
  UsbFolderResponse,
  StartHardwareScanParams,
  HardwareScanStatus,
  ScanHistoryResponse,
} from "../types/ingestion";

// ─── Local Library ────────────────────────────────────────────────────

export function useLibraryDetect(enabled: boolean) {
  return useQuery<LibraryDetectResponse>({
    queryKey: ["local-library", "detect"],
    queryFn: () => apiFetch<LibraryDetectResponse>("/local-library/detect"),
    enabled,
    retry: false,
  });
}

/**
 * GET /api/local-library/status — returns a discriminated union:
 * - { status: "no_scan", message } before any scan
 * - { status: "complete", source, total_tracks, ... } after a scan
 */
export function useLibraryScanStatus(enabled: boolean) {
  return useQuery<LibraryScanStatus>({
    queryKey: ["local-library", "status"],
    queryFn: () => apiFetch<LibraryScanStatus>("/local-library/status"),
    enabled,
    retry: false,
  });
}

export function useLibraryScan() {
  const queryClient = useQueryClient();
  return useMutation<LibraryScanResult, Error, LibraryScanParams>({
    mutationFn: (params) =>
      apiFetch<LibraryScanResult>("/local-library/scan", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["local-library", "status"] });
      queryClient.invalidateQueries({ queryKey: ["tracks"] });
    },
  });
}

// ─── Hardware Scanner (Bridge USB) ────────────────────────────────────

export function useUsbBrowse(player: number, slot: string, enabled: boolean) {
  return useQuery<UsbBrowseResponse>({
    queryKey: ["scanner", "browse", player, slot],
    queryFn: () =>
      apiFetch<UsbBrowseResponse>(`/scanner/browse/${player}/${slot}`),
    enabled,
    retry: false,
  });
}

export function useUsbMenu(player: number, slot: string, enabled: boolean) {
  return useQuery<UsbMenuResponse>({
    queryKey: ["scanner", "menu", player, slot],
    queryFn: () =>
      apiFetch<UsbMenuResponse>(`/scanner/browse/${player}/${slot}/menu`),
    enabled,
    retry: false,
  });
}

export function useUsbFolder(
  player: number,
  slot: string,
  folderId: number | null,
  enabled: boolean,
  isFolder: boolean = true,
) {
  return useQuery<UsbFolderResponse>({
    queryKey: ["scanner", "folder", player, slot, folderId, isFolder],
    queryFn: () =>
      apiFetch<UsbFolderResponse>(
        `/scanner/browse/${player}/${slot}/folder/${folderId}?is_folder=${isFolder}`,
      ),
    enabled: enabled && folderId !== null,
    retry: false,
  });
}

export function useStartHardwareScan() {
  return useMutation<HardwareScanStatus, Error, StartHardwareScanParams>({
    mutationFn: (params) =>
      apiFetch<HardwareScanStatus>("/scanner/start", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    onMutate: () => {
      // Immediately reflect "scan starting" in the UI so the button disables
      // and old progress clears. WS events will take over once they arrive.
      const { setScanProgress } = useIngestionStore.getState();
      setScanProgress({ status: "scanning", scanned: 0, skipped: 0, errors: 0, total: 0, current_track: "", deck_progress: {} });
    },
    onError: () => {
      // Revert optimistic update on failure
      useIngestionStore.getState().clearScanProgress();
    },
  });
}

export function useStopHardwareScan() {
  return useMutation<void, Error>({
    mutationFn: () =>
      apiFetch<void>("/scanner/stop", { method: "POST" }),
  });
}

export function useHardwareScanStatus(enabled: boolean) {
  return useQuery<HardwareScanStatus>({
    queryKey: ["scanner", "status"],
    queryFn: () => apiFetch<HardwareScanStatus>("/scanner/status"),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "scanning") return 2000;
      return false;
    },
    retry: false,
  });
}

export function useScanHistory(enabled: boolean) {
  return useQuery<ScanHistoryResponse>({
    queryKey: ["scanner", "history"],
    queryFn: () => apiFetch<ScanHistoryResponse>("/scanner/history"),
    enabled,
    retry: false,
  });
}
