"use client";

import { Info } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { METRIC_INFO, type MetricKey } from "@/lib/eval/metric-info";

/**
 * A metric label that reveals a structured explanation on hover/focus:
 * what it measures, a simple example, and which values are better.
 *
 * Falls back to plain text if the key is unknown, so it's safe to use as a
 * drop-in label wrapper.
 */
export function MetricLabel({
  metricKey,
  children,
}: {
  metricKey: MetricKey;
  children: React.ReactNode;
}) {
  const info = METRIC_INFO[metricKey];
  if (!info) return <>{children}</>;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          data-testid={`metric-label-${metricKey}`}
          className="inline-flex cursor-help items-center gap-1 underline decoration-dotted decoration-muted-foreground/50 underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          {children}
          <Info className="h-3 w-3 opacity-50" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-semibold">{info.title}</div>
          <p>{info.what}</p>
          <p>
            <span className="font-medium text-foreground/80">Example: </span>
            {info.example}
          </p>
          <p>
            <span className="font-medium text-foreground/80">Better: </span>
            {info.better}
          </p>
          {info.range && (
            <p className="text-muted-foreground">Range: {info.range}</p>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
