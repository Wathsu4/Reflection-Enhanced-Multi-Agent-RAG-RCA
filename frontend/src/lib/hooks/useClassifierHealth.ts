"use client";

import { useQuery } from "@tanstack/react-query";
import {
  getClassifierHealth,
  type HealthResponse,
} from "@/lib/api/classifier";

export type ClassifierHealthStatus = "ok" | "down" | "loading";

export interface UseClassifierHealthResult {
  /** Coarse status used to color the indicator pill. */
  status: ClassifierHealthStatus;
  /** Last successful health payload, if any. */
  data: HealthResponse | undefined;
  /** Last error from a failed poll. */
  error: Error | null;
  /** Whether the underlying query has ever resolved (success or failure). */
  hasResolvedOnce: boolean;
}

/**
 * Polls the classifier service's `/health` endpoint at a fixed interval.
 *
 * Designed for the small "service status" pill in the top nav. The hook
 * intentionally retries only once per poll cycle so a brief blip turns the
 * pill red instead of being silently swallowed by react-query's default
 * exponential backoff.
 */
export function useClassifierHealth(opts: {
  intervalMs?: number;
} = {}): UseClassifierHealthResult {
  const { intervalMs = 10_000 } = opts;

  const query = useQuery({
    queryKey: ["classifier-health"],
    queryFn: ({ signal }) => getClassifierHealth(signal),
    refetchInterval: intervalMs,
    refetchOnWindowFocus: true,
    retry: 1,
    // Short stale time so a manual refetch (e.g. after restarting the
    // service) immediately re-queries instead of returning the cached value.
    staleTime: 5_000,
  });

  let status: ClassifierHealthStatus;
  if (query.isError) {
    status = "down";
  } else if (query.data) {
    status = query.data.status === "ok" && query.data.model_loaded ? "ok" : "down";
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
