/** Network API functions and TanStack Query hooks for interface/route management. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  InterfaceListResponse,
  RouteStatusResponse,
  RouteFixResponse,
  RouteSetupStatus,
  BridgeState,
} from "../types";

// --- Query hooks ---

export function useInterfaces() {
  return useQuery<InterfaceListResponse>({
    queryKey: ["network", "interfaces"],
    queryFn: () => apiFetch<InterfaceListResponse>("/network/interfaces"),
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  });
}

export function useRouteStatus() {
  return useQuery<RouteStatusResponse>({
    queryKey: ["network", "route"],
    queryFn: () => apiFetch<RouteStatusResponse>("/network/route"),
    refetchOnWindowFocus: true,
    staleTime: 5_000,
  });
}

export function useRouteSetupStatus() {
  return useQuery<RouteSetupStatus>({
    queryKey: ["network", "route", "setup-status"],
    queryFn: () => apiFetch<RouteSetupStatus>("/network/route/setup-status"),
    staleTime: 60_000,
  });
}

// --- Mutation functions ---

export async function fixRoute(iface: string): Promise<RouteFixResponse> {
  return apiFetch<RouteFixResponse>("/network/route/fix", {
    method: "POST",
    body: JSON.stringify({ interface: iface }),
  });
}

export async function updateBridgeInterface(iface: string): Promise<unknown> {
  return apiFetch("/bridge/settings", {
    method: "PUT",
    body: JSON.stringify({ network_interface: iface }),
  });
}

export async function restartBridge(): Promise<BridgeState> {
  return apiFetch<BridgeState>("/bridge/restart", {
    method: "POST",
  });
}

// --- Mutation hooks ---

export function useFixRoute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fixRoute,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["network", "route"] });
    },
  });
}

export function useRestartBridge() {
  return useMutation({
    mutationFn: restartBridge,
  });
}
