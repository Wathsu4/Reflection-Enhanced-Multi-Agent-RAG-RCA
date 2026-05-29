"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  cancelJob,
  getJob,
  runExperiment,
  type Job,
} from "@/lib/api/evaluation";

const TERMINAL: ReadonlySet<Job["status"]> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

export interface UseExperimentRunResult {
  /** The job currently being tracked (active or just-finished), if any. */
  job: Job | undefined;
  /** True while a tracked job is still running. */
  isRunning: boolean;
  /** Start a run with the given params. No-op while one is already tracked. */
  run: (params: Record<string, number | boolean>) => void;
  /** Request cancellation of the tracked job. */
  cancel: () => void;
  /** Clear the tracked job (e.g. to start a fresh one after completion). */
  reset: () => void;
  /** Error from the start mutation (e.g. 409 busy, bad params). */
  startError: Error | null;
  isStarting: boolean;
}

/**
 * Drives a single experiment run: a start mutation, then **polling** the
 * job until it reaches a terminal state. Polling (rather than SSE) suits
 * the slow per-scenario cadence and survives reconnects.
 *
 * Pass `adoptJobId` to attach to a job that's already running (e.g. one
 * started from another tab) so its progress shows on load.
 */
export function useExperimentRun(
  experimentId: string,
  opts: { adoptJobId?: string | null; pollMs?: number } = {},
): UseExperimentRunResult {
  const { adoptJobId = null, pollMs = 1_500 } = opts;
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);

  // Adopt an externally-running job once, if we aren't already tracking one.
  useEffect(() => {
    if (adoptJobId && !jobId) setJobId(adoptJobId);
  }, [adoptJobId, jobId]);

  const startMutation = useMutation({
    mutationFn: (params: Record<string, number | boolean>) =>
      runExperiment(experimentId, params),
    onSuccess: (job) => setJobId(job.id),
  });

  const jobQuery = useQuery<Job>({
    queryKey: ["eval", "job", jobId],
    queryFn: ({ signal }) => getJob(jobId as string, signal),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.has(status) ? false : pollMs;
    },
    refetchOnWindowFocus: true,
  });

  const job = jobQuery.data;
  const isRunning = Boolean(job && !TERMINAL.has(job.status));

  // When a tracked job finishes, refresh the experiment detail + list so the
  // history and busy flag update without a manual reload.
  useEffect(() => {
    if (job && TERMINAL.has(job.status)) {
      queryClient.invalidateQueries({ queryKey: ["eval", "experiment", experimentId] });
      queryClient.invalidateQueries({ queryKey: ["eval", "experiments"] });
    }
  }, [job, experimentId, queryClient]);

  const cancelMutation = useMutation({
    mutationFn: () => cancelJob(jobId as string),
  });

  return {
    job,
    isRunning,
    run: (params) => {
      if (!isRunning && !startMutation.isPending) startMutation.mutate(params);
    },
    cancel: () => {
      if (jobId && isRunning) cancelMutation.mutate();
    },
    reset: () => setJobId(null),
    startError: (startMutation.error as Error | null) ?? null,
    isStarting: startMutation.isPending,
  };
}
