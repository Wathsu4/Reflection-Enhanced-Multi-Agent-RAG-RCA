"use client";

/**
 * Polls the classifier service's `/health` endpoint at a fixed interval.
 *
 * Designed for the small "service status" pill in the top nav; the
 * polling behaviour lives in {@link useServiceHealth}.
 */

import {
  getClassifierHealth,
  type HealthResponse,
} from "@/lib/api/classifier";
import {
  type ServiceHealthStatus,
  type UseServiceHealthResult,
  useServiceHealth,
} from "@/lib/hooks/useServiceHealth";

export type ClassifierHealthStatus = ServiceHealthStatus;

export type UseClassifierHealthResult = UseServiceHealthResult<HealthResponse>;

export function useClassifierHealth(opts: {
  intervalMs?: number;
} = {}): UseClassifierHealthResult {
  return useServiceHealth({
    queryKey: "classifier-health",
    fetch: getClassifierHealth,
    isHealthy: (data) => data.status === "ok" && data.model_loaded,
    intervalMs: opts.intervalMs,
  });
}
