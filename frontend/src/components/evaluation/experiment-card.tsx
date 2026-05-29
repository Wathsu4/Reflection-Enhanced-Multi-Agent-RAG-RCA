"use client";

import { ChevronRight, Clock, Sparkles } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Experiment } from "@/lib/api/evaluation";

/** Small coloured chips for the research-question tags. */
export function RqBadges({ tags }: { tags: string[] }) {
  if (!tags.length) return null;
  return (
    <div className="flex flex-wrap gap-1" data-testid="rq-badges">
      {tags.map((t) => (
        <Badge key={t} variant="secondary" className="text-[10px] font-mono">
          {t}
        </Badge>
      ))}
    </div>
  );
}

/**
 * One experiment summary card on the /evaluation landing grid. Planned
 * (not-yet-implemented) experiments render muted and aren't clickable.
 */
export function ExperimentCard({ experiment }: { experiment: Experiment }) {
  const planned = experiment.status === "planned";

  const body = (
    <Card
      data-testid="experiment-card"
      data-experiment-id={experiment.id}
      data-status={experiment.status}
      className={cn(
        "h-full transition-colors",
        planned
          ? "opacity-70"
          : "hover:border-primary/50 hover:bg-muted/40 cursor-pointer",
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base leading-snug">
            {experiment.title}
          </CardTitle>
          {planned ? (
            <Badge variant="outline" className="shrink-0 text-[10px]">
              Planned
            </Badge>
          ) : (
            <Badge className="shrink-0 text-[10px]">Available</Badge>
          )}
        </div>
        <CardDescription className="line-clamp-2">
          {experiment.summary}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-xs text-muted-foreground">
        <RqBadges tags={experiment.rq_tags} />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {experiment.family && (
            <span className="font-mono">{experiment.family}</span>
          )}
          <span className="inline-flex items-center gap-1">
            <Sparkles className="h-3 w-3" />
            {experiment.gemini ? "uses Gemini" : "no Gemini"}
          </span>
          {experiment.expected_runtime && (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {experiment.expected_runtime}
            </span>
          )}
        </div>
        {!planned && (
          <div className="flex items-center gap-1 text-primary">
            Open <ChevronRight className="h-3 w-3" />
          </div>
        )}
      </CardContent>
    </Card>
  );

  if (planned) return body;
  return (
    <Link
      href={`/evaluation/${encodeURIComponent(experiment.id)}`}
      className="block"
      data-testid="experiment-card-link"
    >
      {body}
    </Link>
  );
}
