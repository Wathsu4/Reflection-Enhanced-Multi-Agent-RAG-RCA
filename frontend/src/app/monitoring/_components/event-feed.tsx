"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SEVERITY_COLORS, type SimEvent } from "@/lib/types";
import { cn, formatConfidence } from "@/lib/utils";
import { Loader2, AlertTriangle } from "lucide-react";

function relativeTime(ts: number, now: number): string {
  const diff = Math.max(0, now - ts);
  if (diff < 1000) return "just now";
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return `${Math.floor(diff / 3_600_000)}h ago`;
}

export interface EventFeedProps {
  events: SimEvent[];
  selectedId?: string | null;
  onSelect?: (event: SimEvent) => void;
}

export function EventFeed({ events, selectedId, onSelect }: EventFeedProps) {
  // Lock `now` once per render so all rows agree on the same baseline.
  const now = Date.now();

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle className="text-base">Live Feed</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          {events.length === 0 ? (
            <div
              className="p-6 text-center text-sm text-muted-foreground"
              data-testid="event-feed-empty"
            >
              Click <span className="font-medium">Start</span> to begin
              streaming synthetic logs.
            </div>
          ) : (
            <ul className="divide-y" data-testid="event-feed-list">
              {events.map((event) => {
                const sev =
                  event.classification?.severity ?? event.intendedSeverity;
                const isSelected = event.id === selectedId;
                // True only when classification is back AND it disagrees
                // with the generator's intended severity. Surfaces both
                // classifier mistakes and weak templates during the demo.
                const isMismatch =
                  event.status === "classified" &&
                  event.classification !== null &&
                  event.classification.severity !== event.intendedSeverity;
                return (
                  <li
                    key={event.id}
                    onClick={() => onSelect?.(event)}
                    className={cn(
                      "cursor-pointer space-y-1 px-4 py-3 transition-colors hover:bg-muted/50",
                      isSelected && "bg-muted",
                    )}
                    data-testid="event-feed-row"
                    data-event-id={event.id}
                    data-status={event.status}
                    data-selected={isSelected ? "true" : "false"}
                    data-mismatch={isMismatch ? "true" : "false"}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge
                          className={cn("text-xs", SEVERITY_COLORS[sev])}
                        >
                          {sev.replace(/_/g, " ")}
                        </Badge>
                        {event.status === "pending" && (
                          <Loader2
                            className="h-3 w-3 animate-spin text-muted-foreground"
                            aria-label="classifying"
                          />
                        )}
                        {event.status === "error" && (
                          <AlertTriangle
                            className="h-3 w-3 text-destructive"
                            aria-label="classification failed"
                          />
                        )}
                        {isMismatch && (
                          <AlertTriangle
                            className="h-3 w-3 text-yellow-500"
                            aria-label={`intended ${event.intendedSeverity}, predicted ${event.classification!.severity}`}
                            data-testid="mismatch-indicator"
                          />
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {relativeTime(event.timestamp, now)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span>
                        {event.numLines} line{event.numLines === 1 ? "" : "s"}
                        {" \u00b7 "}
                        intended:{" "}
                        <span className="font-mono">
                          {event.intendedSeverity}
                        </span>
                      </span>
                      {event.classification && (
                        <span className="font-mono">
                          {formatConfidence(event.classification.confidence)}
                        </span>
                      )}
                    </div>
                    {event.status === "error" && event.classifyError && (
                      <p className="truncate text-xs text-destructive">
                        {event.classifyError}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
