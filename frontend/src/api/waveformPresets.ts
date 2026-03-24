/** TanStack Query hooks for /api/waveform-presets endpoints. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  WaveformPreset,
  WaveformPresetsResponse,
  WaveformRenderParams,
} from "../types/waveformPreset";

const KEY = ["waveform-presets"] as const;

export function useWaveformPresets() {
  return useQuery<WaveformPresetsResponse>({
    queryKey: KEY,
    queryFn: () => apiFetch<WaveformPresetsResponse>("/waveform-presets"),
  });
}

export function useActiveWaveformPreset() {
  return useQuery<WaveformPreset>({
    queryKey: [...KEY, "active"],
    queryFn: () => apiFetch<WaveformPreset>("/waveform-presets/active"),
  });
}

export function useCreatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; params: WaveformRenderParams }) =>
      apiFetch<WaveformPreset>("/waveform-presets", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useUpdatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      name?: string;
      params?: WaveformRenderParams;
    }) =>
      apiFetch<WaveformPreset>(`/waveform-presets/${id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDeletePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ status: string }>(`/waveform-presets/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useActivatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<WaveformPreset>(`/waveform-presets/${id}/activate`, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
