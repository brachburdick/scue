/** TanStack Query hooks for /api/tracks endpoints. */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { TrackListResponse } from "../types";

export interface TrackListParams {
  limit?: number;
  offset?: number;
  sort_by?: string;
  sort_desc?: boolean;
}

function buildTrackListUrl(params: TrackListParams): string {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  if (params.sort_by != null) search.set("sort_by", params.sort_by);
  if (params.sort_desc != null) search.set("sort_desc", String(params.sort_desc));
  const qs = search.toString();
  return `/tracks${qs ? `?${qs}` : ""}`;
}

export function useTracks(params: TrackListParams = {}) {
  return useQuery<TrackListResponse>({
    queryKey: ["tracks", params],
    queryFn: () => apiFetch<TrackListResponse>(buildTrackListUrl(params)),
  });
}
