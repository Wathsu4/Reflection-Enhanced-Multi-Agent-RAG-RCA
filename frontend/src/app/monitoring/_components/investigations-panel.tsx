"use client";

/**
 * Compact accordion list of automated RCA investigations.
 *
 * Each row represents one investigation queued by the simulator.
 * Collapsed: severity badge, "X.Xs" or "running…", and the first
 * line of the root cause (extracted heuristically). Expanded: full
 * `AgentTimeline` (raw events fed through the same aggregator that
 * powers the manual /agent-explorer page).
 */

import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleX,
  Loader2,
  Bot,
} from "lucide-react";
import { useState } from "react";

import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { rootCausePreview } from "@/lib/agents/extract-root-cause";
import { aggregateEvents } from "@/lib/hooks/useAgentStream";
import {
  type Investigation,
  SEVERITY_COLORS,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface InvestigationsPanelProps {
  investigations: Investigation[];
  /** True while the user has the auto-RCA toggle enabled. */
  autoRcaEnabled: boolean;
}

export function InvestigationsPanel({
  investigations,
  autoRcaEnabled,
}: InvestigationsPanelProps) {
  if (investigations.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-muted-foreground">
          <Bot className="h-6 w-6" />
          <p className="font-medium">No investigations yet.</p>
          <p className="text-xs">
            {autoRcaEnabled
              ? "When the classifier flags a chunk as ERROR or FATAL, an RCA will run automatically."
              : "Auto-RCA is currently OFF. Toggle it on in the simulator controls to enable automatic investigations."}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div
      className="flex flex-col gap-2 overflow-y-auto"
      data-testid="investigations-panel"
    >
      {investigations.map((inv) => (
        <InvestigationCard key={inv.id} investigation={inv} />
      ))}
    </div>
  );
}

// -------------------- per-investigation --------------------

interface InvestigationCardProps {
  investigation: Investigation;
}

function InvestigationCard({ investigation }: InvestigationCardProps) {
  const [open, setOpen] = useState(false);
  const inv = investigation;

  // Aggregate raw ADK events into per-agent groups for the timeline.
  // Done lazily (only when expanded) since aggregation is O(n) in
  // events and a long-running demo could hold a hundred of these.
  const aggregated = open ? aggregateEvents(inv.events) : null;

  return (
    <Card data-testid="investigation-card" data-status={inv.status}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 p-3 text-left"
      >
        <div className="mt-0.5">
          {open ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              className={cn("font-mono text-[10px]", SEVERITY_COLORS[inv.severity])}
              variant="secondary"
            >
              {inv.severity}
            </Badge>
            <StatusBadge status={inv.status} />
            <span className="text-xs text-muted-foreground">
              {formatDuration(inv)}
            </span>
            <span className="ml-auto truncate font-mono text-[10px] text-muted-foreground">
              {inv.id.slice(0, 8)}
            </span>
          </div>

          <div className="mt-1 truncate text-sm" data-testid="root-cause-preview">
            {summarize(inv)}
          </div>
        </div>
      </button>

      {open && (
        <CardContent className="border-t px-3 pt-3">
          {inv.error && (
            <div className="mb-3 rounded border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
              {inv.error}
            </div>
          )}
          {aggregated ? (
            <AgentTimeline
              status={inv.status === "done" ? "done" : inv.status === "error" ? "error" : "streaming"}
              groups={aggregated}
              finalMarkdown={inv.finalAnswer}
              finalTitle="Final RCA"
            />
          ) : null}
        </CardContent>
      )}
    </Card>
  );
}

// -------------------- helpers --------------------

function StatusBadge({ status }: { status: Investigation["status"] }) {
  switch (status) {
    case "queued":
      return (
        <Badge variant="outline" className="gap-1 text-muted-foreground">
          <CircleAlert className="h-3 w-3" />
          queued
        </Badge>
      );
    case "running":
      return (
        <Badge variant="outline" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          running
        </Badge>
      );
    case "done":
      return (
        <Badge variant="secondary" className="gap-1">
          <CircleCheck className="h-3 w-3 text-emerald-500" />
          done
        </Badge>
      );
    case "error":
      return (
        <Badge variant="destructive" className="gap-1">
          <CircleX className="h-3 w-3" />
          error
        </Badge>
      );
  }
}

function formatDuration(inv: Investigation): string {
  if (inv.status === "queued") return "queued…";
  if (inv.status === "running") return "running…";
  if (!inv.completedAt) return "";
  const ms = inv.completedAt - inv.startedAt;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function summarize(inv: Investigation): string {
  if (inv.status === "queued") return "Waiting in queue…";
  if (inv.status === "running" && !inv.finalAnswer)
    return "Investigating — agents are working…";
  if (inv.status === "error" && inv.error)
    return inv.error;
  const preview = rootCausePreview(inv.finalAnswer ?? "", 140);
  return preview || "(no root cause extracted)";
}
