"use client";

/**
 * Visual timeline of an RCA pipeline run.
 *
 * Renders one card per sub-agent (one entry in `groups`), shows tool
 * calls as collapsible details, and surfaces a final markdown summary
 * card at the bottom when the pipeline completes.
 *
 * Pure presentational component: takes `groups` + a `finalMarkdown`
 * string + a `status` indicator. State management belongs in the page
 * (via `useAgentStream`), not here.
 */

import {
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Database,
  Eye,
  Loader2,
  Search,
  Wrench,
} from "lucide-react";
import { useState, type ComponentType } from "react";

import { MarkdownView } from "@/components/agents/MarkdownView";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentRunStatus } from "@/lib/hooks/useAgentStream";
import type { AgentRunGroup, AgentToolInvocation } from "@/lib/types";
import { cn } from "@/lib/utils";

// Re-export the hook's status type so call sites that need it can
// import from one place (the component) rather than the hook.
export type { AgentRunStatus };

interface AgentTimelineProps {
  status: AgentRunStatus;
  groups: AgentRunGroup[];
  finalMarkdown: string | null;
  /** Optional override for the bottom-card title; defaults to "Final RCA". */
  finalTitle?: string;
}

// -------------------- agent metadata --------------------
// Map from sub-agent name to display props. Unknown agents fall through
// to a generic Bot icon and the raw name -- this avoids breaking the UI
// when Phase 9+ adds new agents we haven't styled yet.

interface AgentMeta {
  label: string;
  description: string;
  Icon: ComponentType<{ className?: string }>;
}

const AGENT_META: Record<string, AgentMeta> = {
  retrieval_agent: {
    label: "Retrieval",
    description: "Pulls similar past incidents from the knowledge base.",
    Icon: Search,
  },
  reasoning_agent: {
    label: "Reasoning",
    description: "Generates a root-cause hypothesis from retrieval results.",
    Icon: Brain,
  },
  reflection_agent: {
    label: "Reflection",
    description: "Critiques the hypothesis and scores incident relevance.",
    Icon: Eye,
  },
  memory_update_agent: {
    label: "Memory update",
    description: "Persists score deltas and writes the operator summary.",
    Icon: Database,
  },
};

function metaFor(author: string): AgentMeta {
  return (
    AGENT_META[author] ?? {
      label: author,
      description: "Agent step.",
      Icon: Bot,
    }
  );
}

// -------------------- main component --------------------

export function AgentTimeline({
  status,
  groups,
  finalMarkdown,
  finalTitle = "Final RCA",
}: AgentTimelineProps) {
  if (status === "idle" && groups.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-muted-foreground">
          <Bot className="h-6 w-6" />
          <p>Run an analysis to see the agent pipeline here.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3" data-testid="agent-timeline">
      {groups.map((group, idx) => (
        <AgentStepCard
          key={`${group.author}-${idx}`}
          group={group}
          isLastGroup={idx === groups.length - 1}
          parentStatus={status}
        />
      ))}

      {status === "streaming" && groups.length === 0 && <PendingPlaceholder />}

      {finalMarkdown && (
        <Card className="border-primary/30" data-testid="final-rca-card">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              {finalTitle}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MarkdownView markdown={finalMarkdown} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// -------------------- per-agent step --------------------

interface AgentStepCardProps {
  group: AgentRunGroup;
  isLastGroup: boolean;
  parentStatus: AgentRunStatus;
}

function AgentStepCard({ group, isLastGroup, parentStatus }: AgentStepCardProps) {
  const meta = metaFor(group.author);
  // The "currently working" agent is: the last group in the list
  // while the parent status is still streaming AND this group hasn't
  // yet been marked complete via stateDelta or partial:false.
  const isWorking = parentStatus === "streaming" && isLastGroup && !group.isComplete;

  return (
    <Card data-testid="agent-step" data-author={group.author}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <meta.Icon className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm font-semibold">{meta.label}</CardTitle>
          <span className="text-xs text-muted-foreground">{group.author}</span>
        </div>
        <StepStatusBadge isWorking={isWorking} isComplete={group.isComplete} />
      </CardHeader>
      <CardContent className="pt-0">
        {meta.description && (
          <p className="mb-2 text-xs text-muted-foreground">{meta.description}</p>
        )}

        {group.toolInvocations.map((tool) => (
          <ToolCallCard key={tool.callId} tool={tool} />
        ))}

        {group.text && (
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted/60 p-2 text-xs whitespace-pre-wrap font-mono">
            {stripJsonFences(group.text)}
          </pre>
        )}

        {!group.text && !group.toolInvocations.length && isWorking && (
          <Skeleton className="mt-2 h-4 w-3/4" />
        )}
      </CardContent>
    </Card>
  );
}

function StepStatusBadge({
  isWorking,
  isComplete,
}: {
  isWorking: boolean;
  isComplete: boolean;
}) {
  if (isComplete) {
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
        done
      </Badge>
    );
  }
  if (isWorking) {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        working
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground">
      <CircleAlert className="h-3 w-3" />
      pending
    </Badge>
  );
}

// -------------------- tool call card --------------------

function ToolCallCard({ tool }: { tool: AgentToolInvocation }) {
  const [open, setOpen] = useState(false);
  const hasResponse = tool.response !== undefined;

  return (
    <div
      className="my-2 rounded border bg-background"
      data-testid="tool-call-card"
      data-tool-name={tool.name}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Wrench className="h-3 w-3 text-muted-foreground" />
        <span className="font-mono font-medium">{tool.name}</span>
        <span className="text-muted-foreground">
          ({Object.keys(tool.args).length} args
          {hasResponse ? ", responded" : ", pending"})
        </span>
      </button>
      {open && (
        <div className="border-t px-2 py-2 text-xs">
          <div className="mb-1 font-semibold text-muted-foreground">args</div>
          <pre className="overflow-auto rounded bg-muted/60 p-2 font-mono text-[11px]">
            {safeJson(tool.args)}
          </pre>
          {hasResponse && (
            <>
              <div className="mt-2 mb-1 font-semibold text-muted-foreground">
                response
              </div>
              <pre className="max-h-48 overflow-auto rounded bg-muted/60 p-2 font-mono text-[11px]">
                {safeJson(tool.response)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function PendingPlaceholder() {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Waiting for the first agent to respond…
      </CardContent>
    </Card>
  );
}

// -------------------- helpers --------------------

/**
 * Strip the optional ```json ... ``` fences that Gemini occasionally
 * wraps around JSON output despite our prompts. Keeping the visible
 * pre-block clean makes the UI more readable; the underlying state
 * we hand to downstream agents is unaffected since this is display-only.
 */
export function stripJsonFences(text: string): string {
  const trimmed = text.trim();
  const fenceRe = /^```(?:json)?\s*\n?([\s\S]*?)\n?```$/;
  const m = trimmed.match(fenceRe);
  return m ? m[1].trim() : text;
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    // Cyclic structures or BigInt etc. -- fall back to a string repr.
    return String(value);
  }
}

