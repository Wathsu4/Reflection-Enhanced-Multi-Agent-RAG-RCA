"use client";

/**
 * Small live indicator showing whether the classifier service is reachable.
 * Lives in the top nav. Re-checks every 10s via {@link useClassifierHealth}.
 */

import { StatusPill } from "@/components/status-pill";
import { useClassifierHealth } from "@/lib/hooks/useClassifierHealth";

const LABELS = {
  ok: "Classifier",
  down: "Classifier offline",
  loading: "Checking…",
} as const;

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
    <StatusPill
      status={status}
      label={LABELS[status]}
      tooltip={tooltip}
      detail={data?.device}
      testId="service-status-pill"
    />
  );
}
