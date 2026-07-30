"use client";

/**
 * Presentational pill shared by the top-nav service indicators
 * ({@link ServiceStatusPill} for the classifier, {@link AgentStatusPill}
 * for the agent service) so they stay visually consistent. The health
 * polling and the wording live in the wrappers.
 */

import type { ServiceHealthStatus } from "@/lib/hooks/useServiceHealth";
import { cn } from "@/lib/utils";

const DOT_STYLES: Record<ServiceHealthStatus, string> = {
  ok: "bg-green-500",
  down: "bg-red-500",
  loading: "bg-gray-400 animate-pulse",
};

export interface StatusPillProps {
  status: ServiceHealthStatus;
  label: string;
  tooltip: string;
  /** Extra detail shown next to the label when the service is up. */
  detail?: string | null;
  detailClassName?: string;
  testId: string;
}

export function StatusPill({
  status,
  label,
  tooltip,
  detail,
  detailClassName,
  testId,
}: StatusPillProps) {
  return (
    <div
      className="flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs"
      title={tooltip}
      role="status"
      aria-live="polite"
      data-testid={testId}
      data-status={status}
    >
      <span
        className={cn("h-2 w-2 rounded-full", DOT_STYLES[status])}
        aria-hidden="true"
      />
      <span className="font-medium">{label}</span>
      {status === "ok" && detail && (
        <span className={cn("text-muted-foreground", detailClassName)}>
          · {detail}
        </span>
      )}
    </div>
  );
}
