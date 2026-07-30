"use client";

/**
 * Live indicator for the ADK agent service. Mirrors `ServiceStatusPill`
 * (which tracks the classifier service) so the two read consistently
 * in the top nav. Re-checks every 10s via {@link useAgentHealth}.
 */

import { StatusPill } from "@/components/status-pill";
import { useAgentHealth } from "@/lib/hooks/useAgentHealth";

const LABELS = {
  ok: "Agent",
  down: "Agent offline",
  loading: "Checking…",
} as const;

export function AgentStatusPill() {
  const { status, data } = useAgentHealth();

  const tooltip =
    status === "ok"
      ? `Online — ${data?.model ?? "model unknown"}`
      : status === "down"
        ? "Agent service unreachable. Is uvicorn running on :8000?"
        : "Probing agent service…";

  return (
    <StatusPill
      status={status}
      label={LABELS[status]}
      tooltip={tooltip}
      detail={data?.model?.replace(/^gemini-/, "")}
      detailClassName="hidden sm:inline"
      testId="agent-status-pill"
    />
  );
}
