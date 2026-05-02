"use client";

/**
 * Polls the agent service's `/health` endpoint at a fixed interval.
 *
 * Mirrors `useClassifierHealth` so both pills in the top nav share a
 * known-good shape. We intentionally retry only once per poll cycle so
 * a brief blip flips the pill red instead of being silently swallowed
 * by react-query's exponential backoff.
 */

import { useQuery } from "@tanstack/react-query";

import {
  type AgentHealthResponse,
  getAgentHealth,
} from "@/lib/api/agents";

export type AgentHealthStatus = "ok" | "down" | "loading";

export interface UseAgentHealthResult {
  status: AgentHealthStatus;
  data: AgentHealthResponse | undefined;
  error: Error | null;
  hasResolvedOnce: boolean;
}

export function useAgentHealth(opts: { intervalMs?: number } = {}): UseAgentHealthResult {
  const { intervalMs = 10_000 } = opts;

  const query = useQuery({
    queryKey: ["agent-health"],
    queryFn: ({ signal }) => getAgentHealth(signal),
    refetchInterval: intervalMs,
    refetchOnWindowFocus: true,
    retry: 1,
    staleTime: 5_000,
  });

  let status: AgentHealthStatus;
  if (query.isError) {
    status = "down";
  } else if (query.data) {
    // The agent service's only failure mode at /health level is a
    // missing / wrong model name; treat anything else as up.
    status = query.data.status === "ok" ? "ok" : "down";
  } else {
    status = "loading";
  }

  return {
    status,
    data: query.data,
    error: (query.error as Error | null) ?? null,
    hasResolvedOnce: query.isFetched,
  };
}
