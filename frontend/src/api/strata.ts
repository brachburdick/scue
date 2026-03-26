/** TanStack Query hooks for /api/strata endpoints. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  AnalysisSource,
  AnalyzeStrataResult,
  ArrangementFormula,
  ReanalyzeResponse,
  StrataAllTiersResponse,
  StrataBatchStatus,
  StrataJobStatus,
  StrataListResponse,
  StrataTier,
  StrataTierResponse,
  TrackVersionsResponse,
} from "../types/strata";

export function useStrataList() {
  return useQuery<StrataListResponse>({
    queryKey: ["strata-list"],
    queryFn: () => apiFetch<StrataListResponse>("/strata"),
  });
}

export function useStrataAllTiers(fingerprint: string | null) {
  return useQuery<StrataAllTiersResponse>({
    queryKey: ["strata", fingerprint],
    queryFn: () => apiFetch<StrataAllTiersResponse>(`/tracks/${fingerprint}/strata`),
    enabled: fingerprint !== null,
    retry: false,
  });
}

export function useStrataTier(fingerprint: string | null, tier: StrataTier) {
  return useQuery<StrataTierResponse>({
    queryKey: ["strata", fingerprint, tier],
    queryFn: () =>
      apiFetch<StrataTierResponse>(`/tracks/${fingerprint}/strata/${tier}`),
    enabled: fingerprint !== null,
    retry: false,
  });
}

export function useStrataTierWithSource(
  fingerprint: string | null,
  tier: StrataTier,
  source: AnalysisSource,
) {
  return useQuery<StrataTierResponse>({
    queryKey: ["strata", fingerprint, tier, source],
    queryFn: () =>
      apiFetch<StrataTierResponse>(
        `/tracks/${fingerprint}/strata/${tier}?source=${source}`,
      ),
    enabled: fingerprint !== null,
    retry: false,
  });
}

export function useSaveStrata(fingerprint: string | null, tier: StrataTier) {
  const queryClient = useQueryClient();
  return useMutation<{ ok: boolean; tier: string }, Error, { formula: Record<string, unknown> }>({
    mutationFn: ({ formula }) =>
      apiFetch<{ ok: boolean; tier: string }>(`/tracks/${fingerprint}/strata/${tier}`, {
        method: "PUT",
        body: JSON.stringify({ formula }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strata", fingerprint] });
    },
  });
}

export function useAnalyzeStrata(fingerprint: string | null) {
  const queryClient = useQueryClient();
  return useMutation<
    AnalyzeStrataResult,
    Error,
    { tiers: StrataTier[]; analysis_source?: AnalysisSource }
  >({
    mutationFn: ({ tiers, analysis_source }) =>
      apiFetch<AnalyzeStrataResult>(`/tracks/${fingerprint}/strata/analyze`, {
        method: "POST",
        body: JSON.stringify({ tiers, analysis_source }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strata", fingerprint] });
    },
  });
}

/** Poll a strata analysis job for progress (standard/deep tiers). */
export function useStrataJobStatus(jobId: string | null) {
  return useQuery<StrataJobStatus>({
    queryKey: ["strata-job", jobId],
    queryFn: () => apiFetch<StrataJobStatus>(`/strata/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "complete" || status === "failed") return false;
      return 1000;
    },
  });
}

/** Poll a strata batch job for progress. */
export function useStrataBatchStatus(batchId: string | null) {
  return useQuery<StrataBatchStatus>({
    queryKey: ["strata-batch", batchId],
    queryFn: () => apiFetch<StrataBatchStatus>(`/strata/batch/${batchId}`),
    enabled: !!batchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "complete" || status === "failed") return false;
      return 1500;
    },
  });
}

/** Trigger batch strata analysis for multiple tracks. */
export function useAnalyzeStrataBatch() {
  const queryClient = useQueryClient();
  return useMutation<
    StrataBatchStatus,
    Error,
    { fingerprints: string[]; tiers: StrataTier[] }
  >({
    mutationFn: ({ fingerprints, tiers }) =>
      apiFetch<StrataBatchStatus>("/strata/analyze-batch", {
        method: "POST",
        body: JSON.stringify({ fingerprints, tiers }),
      }),
    onSuccess: (data) => {
      // Invalidate strata data for all affected fingerprints on completion
      for (const job of data.jobs) {
        queryClient.invalidateQueries({ queryKey: ["strata", job.fingerprint] });
      }
    },
  });
}

export function useReanalyze(fingerprint: string | null) {
  const queryClient = useQueryClient();
  return useMutation<ReanalyzeResponse, Error>({
    mutationFn: () =>
      apiFetch<ReanalyzeResponse>(`/tracks/${fingerprint}/reanalyze`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strata", fingerprint] });
      queryClient.invalidateQueries({ queryKey: ["track-versions", fingerprint] });
    },
  });
}

export function useTrackVersions(fingerprint: string | null) {
  return useQuery<TrackVersionsResponse>({
    queryKey: ["track-versions", fingerprint],
    queryFn: () =>
      apiFetch<TrackVersionsResponse>(`/tracks/${fingerprint}/versions`),
    enabled: fingerprint !== null,
    retry: false,
  });
}

/** Live strata response: per-player formulas from Pioneer hardware data. */
interface LiveStrataResponse {
  players: Record<string, ArrangementFormula>;
}

/**
 * Poll live strata from all active players.
 * Enabled only when the Live tier is selected + hardware is connected.
 * Polls every 2s so the data stays fresh as tracks change.
 */
export function useLiveStrata(enabled: boolean) {
  return useQuery<LiveStrataResponse>({
    queryKey: ["strata-live"],
    queryFn: () => apiFetch<LiveStrataResponse>("/strata/live"),
    enabled,
    refetchInterval: 2000,
    retry: false,
  });
}
