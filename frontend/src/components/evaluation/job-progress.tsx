"use client";

import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Job } from "@/lib/api/evaluation";

const STATUS_LABEL: Record<Job["status"], string> = {
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

function StatusBadge({ status }: { status: Job["status"] }) {
  if (status === "running") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" /> {STATUS_LABEL[status]}
      </Badge>
    );
  }
  if (status === "succeeded") {
    return (
      <Badge className="gap-1">
        <CheckCircle2 className="h-3 w-3" /> {STATUS_LABEL[status]}
      </Badge>
    );
  }
  return (
    <Badge variant="destructive" className="gap-1">
      <XCircle className="h-3 w-3" /> {STATUS_LABEL[status]}
    </Badge>
  );
}

/**
 * Live view of a running (or finished) job: status, a determinate
 * progress bar driven by scenario count, and a scrolling log tail.
 */
export function JobProgress({ job }: { job: Job }) {
  const { done, total, phase } = job.progress;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="flex flex-col gap-3" data-testid="job-progress">
      <div className="flex items-center justify-between gap-2">
        <StatusBadge status={job.status} />
        <span className="font-mono text-xs text-muted-foreground">
          {phase} · {done}/{total || "?"}
        </span>
      </div>

      <Progress value={pct} data-testid="job-progress-bar" />

      {job.error && (
        <p className="text-xs text-destructive" data-testid="job-error">
          {job.error}
        </p>
      )}

      {job.log_tail.length > 0 && (
        <ScrollArea className="h-40 rounded border bg-muted/30">
          <pre
            className="p-2 text-[11px] leading-relaxed whitespace-pre-wrap"
            data-testid="job-log"
          >
            {job.log_tail.join("\n")}
          </pre>
        </ScrollArea>
      )}
    </div>
  );
}
