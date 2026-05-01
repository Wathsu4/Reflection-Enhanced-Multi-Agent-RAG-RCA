"use client";

import { useClassifierHealth } from "@/lib/hooks/useClassifierHealth";
import { cn } from "@/lib/utils";

const DOT_STYLES = {
  ok: "bg-green-500",
  down: "bg-red-500",
  loading: "bg-gray-400 animate-pulse",
} as const;

const LABELS = {
  ok: "Classifier",
  down: "Classifier offline",
  loading: "Checking…",
} as const;

/**
 * Small live indicator showing whether the classifier service is reachable.
 * Lives in the top nav. Re-checks every 10s via {@link useClassifierHealth}.
 */
export function ServiceStatusPill() {
  const { status, data } = useClassifierHealth();

  // Tooltip text: include device when up so curious devs can see it at a glance.
  const tooltip =
    status === "ok"
      ? `Online — model loaded on ${data?.device ?? "?"}`
      : status === "down"
      ? "Classifier service unreachable. Is uvicorn running on :8001?"
      : "Probing classifier service…";

  return (
    <div
      className="flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs"
      title={tooltip}
      role="status"
      aria-live="polite"
      data-testid="service-status-pill"
      data-status={status}
    >
      <span
        className={cn("h-2 w-2 rounded-full", DOT_STYLES[status])}
        aria-hidden="true"
      />
      <span className="font-medium">{LABELS[status]}</span>
      {status === "ok" && data?.device && (
        <span className="text-muted-foreground">· {data.device}</span>
      )}
    </div>
  );
}
