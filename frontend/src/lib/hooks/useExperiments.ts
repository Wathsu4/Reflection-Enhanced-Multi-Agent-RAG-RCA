"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getExperiment,
  listExperiments,
  type ExperimentDetailResponse,
  type ExperimentListResponse,
} from "@/lib/api/evaluation";

/**
 * Lists all evaluation experiments from the backend registry.
 *
 * Polls on a slow interval so the `busy` flag (whether a job is running)
 * stays roughly current across the landing page and detail pages without
 * a manual refresh.
 */
export function useExperiments(opts: { intervalMs?: number } = {}) {
  const { intervalMs = 5_000 } = opts;
  return useQuery<ExperimentListResponse>({
    queryKey: ["eval", "experiments"],
    queryFn: ({ signal }) => listExperiments(signal),
    refetchInterval: intervalMs,
    refetchOnWindowFocus: true,
    retry: 1,
    staleTime: 2_000,
  });
}

/**
 * Fetches one experiment plus its past-result history. Polls so newly
 * finished runs appear in the history list.
 */
export function useExperimentDetail(
  id: string | undefined,
  opts: { intervalMs?: number } = {},
) {
  const { intervalMs = 5_000 } = opts;
  return useQuery<ExperimentDetailResponse>({
    queryKey: ["eval", "experiment", id],
    queryFn: ({ signal }) => getExperiment(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: intervalMs,
    refetchOnWindowFocus: true,
    retry: 1,
    staleTime: 2_000,
  });
}
