"use client";

/**
 * Replay a single saved RCA session by its id.
 *
 * Fetches the session from ADK's `/apps/.../sessions/{id}` endpoint,
 * then feeds its persisted events through the same aggregator the
 * live stream uses. The `AgentTimeline` thus renders identically for
 * live and replayed runs -- which is exactly the design we wanted.
 */

import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { type AdkSession, getSession } from "@/lib/api/agents";
import { aggregateEvents } from "@/lib/hooks/useAgentStream";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; session: AdkSession }
  | { kind: "error"; message: string };

export default function IncidentReplayPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    getSession(id)
      .then((session) => {
        if (!cancelled) setState({ kind: "ok", session });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Aggregate events into the per-agent groups the timeline renders.
  // useMemo so we don't recompute every keystroke / render unrelated to id.
  const aggregated = useMemo(() => {
    if (state.kind !== "ok") return null;
    const groups = aggregateEvents(state.session.events);
    const finalMarkdown =
      typeof state.session.state.final_output === "string"
        ? (state.session.state.final_output as string)
        : null;
    return { groups, finalMarkdown };
  }, [state]);

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div>
        <Button asChild variant="ghost" size="sm" className="gap-1">
          <Link href="/incidents">
            <ArrowLeft className="h-4 w-4" />
            Back to history
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Session replay</CardTitle>
          <CardDescription className="font-mono text-xs">{id}</CardDescription>
        </CardHeader>
        {state.kind === "ok" && (
          <CardContent className="text-xs text-muted-foreground">
            {state.session.events.length} event(s) ·{" "}
            {Object.keys(state.session.state).length} state key(s)
          </CardContent>
        )}
      </Card>

      {state.kind === "loading" && (
        <Card>
          <CardContent className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading session…
          </CardContent>
        </Card>
      )}

      {state.kind === "error" && (
        <Alert variant="destructive" data-testid="replay-error-alert">
          <AlertTitle>Could not load session</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}

      {aggregated && (
        <AgentTimeline
          status="done"
          groups={aggregated.groups}
          finalMarkdown={aggregated.finalMarkdown}
          finalTitle="Final RCA (replay)"
        />
      )}
    </div>
  );
}
