"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, Sparkles } from "lucide-react";
import {
  SEVERITY_COLORS,
  SEVERITY_ORDER,
  type SimEvent,
} from "@/lib/types";
import { cn, formatConfidence } from "@/lib/utils";

export interface LatestEventCardProps {
  event: SimEvent | null;
}

export function LatestEventCard({ event }: LatestEventCardProps) {
  if (!event) {
    return (
      <Card className="flex h-full items-center justify-center">
        <CardContent
          className="text-center text-sm text-muted-foreground"
          data-testid="latest-event-empty"
        >
          No event selected. Start the simulator or click an event in the feed.
        </CardContent>
      </Card>
    );
  }

  const result = event.classification;
  const displaySeverity = result?.severity ?? event.intendedSeverity;

  return (
    <Card className="flex h-full flex-col" data-testid="latest-event-card">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">
              {result ? "Latest classification" : "Awaiting classification"}
            </CardTitle>
            <CardDescription>
              Intended severity: {event.intendedSeverity} · {event.numLines}{" "}
              lines
            </CardDescription>
          </div>
          <Badge className={cn("text-sm", SEVERITY_COLORS[displaySeverity])}>
            {displaySeverity.replace(/_/g, " ")}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-4 overflow-hidden">
        {!result && event.status === "pending" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Classifying…
          </div>
        )}

        {event.status === "error" && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
            {event.classifyError ?? "Classification failed."}
          </div>
        )}

        {result && (
          <>
            <div>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Confidence</span>
                <span className="font-mono">
                  {formatConfidence(result.confidence)}
                </span>
              </div>
              <Progress value={result.confidence * 100} />
            </div>

            <div className="space-y-1.5">
              {SEVERITY_ORDER.map((s) => (
                <div key={s} className="flex items-center gap-2 text-xs">
                  <div className="w-28 capitalize text-muted-foreground">
                    {s.replace(/_/g, " ").toLowerCase()}
                  </div>
                  <Progress
                    value={result.all_probabilities[s] * 100}
                    className="flex-1"
                  />
                  <div className="w-12 text-right font-mono">
                    {formatConfidence(result.all_probabilities[s])}
                  </div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md border p-2">
                <div className="text-muted-foreground">Priority</div>
                <div className="font-medium capitalize">{result.priority}</div>
              </div>
              <div className="rounded-md border p-2">
                <div className="text-muted-foreground">Inference</div>
                <div className="font-mono">
                  {result.inference_ms.toFixed(1)} ms
                </div>
              </div>
            </div>

            <Button
              className="w-full"
              disabled={!result.should_invoke_rca}
              title={
                result.should_invoke_rca
                  ? "Investigate with the RCA agent (Phase 8)"
                  : "Severity below RCA trigger threshold"
              }
              data-testid="investigate-button"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {result.should_invoke_rca
                ? "Investigate with RCA"
                : "RCA not warranted"}
            </Button>
          </>
        )}

        <div>
          <div className="mb-1 text-xs text-muted-foreground">Log chunk</div>
          <ScrollArea className="h-32 rounded-md border bg-muted/30 p-2">
            <pre
              className="whitespace-pre-wrap font-mono text-xs"
              data-testid="latest-event-chunk"
            >
              {event.chunkText}
            </pre>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
