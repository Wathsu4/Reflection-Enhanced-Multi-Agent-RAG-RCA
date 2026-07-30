"use client";

/**
 * Polls the agent service's `/health` endpoint at a fixed interval.
 *
 * Mirrors `useClassifierHealth` so both pills in the top nav share a
 * known-good shape; the polling behaviour lives in
 * {@link useServiceHealth}.
 */

import {
  type ServiceHealthStatus,
  type UseServiceHealthResult,
  useServiceHealth,
} from "@/lib/hooks/useServiceHealth";
import {
  type AgentHealthResponse,
  getAgentHealth,
} from "@/lib/api/agents";

export type AgentHealthStatus = ServiceHealthStatus;

export type UseAgentHealthResult = UseServiceHealthResult<AgentHealthResponse>;

export function useAgentHealth(opts: { intervalMs?: number } = {}): UseAgentHealthResult {
  return useServiceHealth({
    queryKey: "agent-health",
    fetch: getAgentHealth,
    // The agent service's only failure mode at /health level is a
    // missing / wrong model name; treat anything else as up.
    isHealthy: (data) => data.status === "ok",
    intervalMs: opts.intervalMs,
  });
}
