/** TanStack Query hooks for /api/strata endpoints. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  AnalysisSource,
  ReanalyzeResponse,
  StrataAllTiersResponse,
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

interface AnalyzeStrataResult {
  fingerprint: string;
  completed_tiers?: string[];
  requested_tiers?: string[];
  analysis_source?: string;
  status: string;
  message?: string;
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
