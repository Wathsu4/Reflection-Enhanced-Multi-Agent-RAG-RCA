"use client";

/**
 * Live indicator for the ADK agent service. Mirrors `ServiceStatusPill`
 * (which tracks the classifier service) so the two read consistently
 * in the top nav. Re-checks every 10s via {@link useAgentHealth}.
 */

import { useAgentHealth } from "@/lib/hooks/useAgentHealth";
import { cn } from "@/lib/utils";

const DOT_STYLES = {
  ok: "bg-green-500",
  down: "bg-red-500",
  loading: "bg-gray-400 animate-pulse",
} as const;

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
    <div
      className="flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs"
      title={tooltip}
      role="status"
      aria-live="polite"
      data-testid="agent-status-pill"
      data-status={status}
    >
      <span
        className={cn("h-2 w-2 rounded-full", DOT_STYLES[status])}
        aria-hidden="true"
      />
      <span className="font-medium">{LABELS[status]}</span>
      {status === "ok" && data?.model && (
        <span className="text-muted-foreground hidden sm:inline">
          · {data.model.replace(/^gemini-/, "")}
        </span>
      )}
    </div>
  );
}
