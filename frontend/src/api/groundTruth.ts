/** React Query hooks for ground truth annotation CRUD + scoring. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  GroundTruthEvent,
  GroundTruthResponse,
  GroundTruthListResponse,
  ScoreResponse,
} from "../types/groundTruth";

const API = "/api/ground-truth";

// --- Queries ---

export function useGroundTruth(fingerprint: string | null) {
  return useQuery<GroundTruthResponse>({
    queryKey: ["ground-truth", fingerprint],
    queryFn: async () => {
      const res = await fetch(`${API}/${fingerprint}`);
      if (res.status === 404) return { fingerprint: fingerprint!, events: [], updated_at: null };
      if (!res.ok) throw new Error("Failed to load ground truth");
      return res.json();
    },
    enabled: !!fingerprint,
  });
}

export function useGroundTruthList() {
  return useQuery<GroundTruthListResponse>({
    queryKey: ["ground-truth-list"],
    queryFn: async () => {
      const res = await fetch(API);
      if (!res.ok) throw new Error("Failed to list ground truth");
      return res.json();
    },
  });
}

// --- Mutations ---

export function useSaveGroundTruth() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      fingerprint,
      events,
    }: {
      fingerprint: string;
      events: GroundTruthEvent[];
    }) => {
      const res = await fetch(`${API}/${fingerprint}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events }),
      });
      if (!res.ok) throw new Error("Failed to save ground truth");
      return res.json();
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["ground-truth", variables.fingerprint] });
      qc.invalidateQueries({ queryKey: ["ground-truth-list"] });
    },
  });
}

export function useDeleteGroundTruth() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (fingerprint: string) => {
      const res = await fetch(`${API}/${fingerprint}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete ground truth");
      return res.json();
    },
    onSuccess: (_data, fingerprint) => {
      qc.invalidateQueries({ queryKey: ["ground-truth", fingerprint] });
      qc.invalidateQueries({ queryKey: ["ground-truth-list"] });
    },
  });
}

export function useScoreGroundTruth() {
  return useMutation<ScoreResponse, Error, string>({
    mutationFn: async (fingerprint: string) => {
      const res = await fetch(`${API}/${fingerprint}/score`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to score ground truth");
      return res.json();
    },
  });
}
