"use client";

/**
 * Shared `/health` polling used by {@link useClassifierHealth} and
 * {@link useAgentHealth}.
 *
 * Designed for the small "service status" pills in the top nav. We
 * intentionally retry only once per poll cycle so a brief blip turns the
 * pill red instead of being silently swallowed by react-query's default
 * exponential backoff.
 */

import { useQuery } from "@tanstack/react-query";

export type ServiceHealthStatus = "ok" | "down" | "loading";

export interface UseServiceHealthResult<T> {
  /** Coarse status used to color the indicator pill. */
  status: ServiceHealthStatus;
  /** Last successful health payload, if any. */
  data: T | undefined;
  /** Last error from a failed poll. */
  error: Error | null;
  /** Whether the underlying query has ever resolved (success or failure). */
  hasResolvedOnce: boolean;
}

export interface UseServiceHealthOptions<T> {
  queryKey: string;
  fetch: (signal?: AbortSignal) => Promise<T>;
  /** Service-specific reading of a successful payload. */
  isHealthy: (data: T) => boolean;
  intervalMs?: number;
}

export function useServiceHealth<T>({
  queryKey,
  fetch,
  isHealthy,
  intervalMs = 10_000,
}: UseServiceHealthOptions<T>): UseServiceHealthResult<T> {
  const query = useQuery({
    queryKey: [queryKey],
    queryFn: ({ signal }) => fetch(signal),
    refetchInterval: intervalMs,
    refetchOnWindowFocus: true,
    retry: 1,
    // Short stale time so a manual refetch (e.g. after restarting the
    // service) immediately re-queries instead of returning the cached value.
    staleTime: 5_000,
  });

  let status: ServiceHealthStatus;
  if (query.isError) {
    status = "down";
  } else if (query.data) {
    status = isHealthy(query.data) ? "ok" : "down";
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
