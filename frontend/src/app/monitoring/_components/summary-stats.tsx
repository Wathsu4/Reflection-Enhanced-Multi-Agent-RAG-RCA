"use client";

import { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { SimEvent } from "@/lib/types";

export interface SummaryStatsProps {
  events: SimEvent[];
}

interface ComputedStats {
  total: number;
  classified: number;
  errorPct: number;
  fatalPct: number;
  mismatchPct: number;
  meanInferenceMs: number | null;
}

/**
 * Pure function so it's trivially unit-testable apart from the React shell.
 * Exported for the test file.
 */
export function computeStats(events: SimEvent[]): ComputedStats {
  const total = events.length;
  const classified = events.filter((e) => e.classification !== null);
  const classifiedCount = classified.length;

  const errorCount = classified.filter(
    (e) => e.classification!.severity === "ERROR",
  ).length;
  const fatalCount = classified.filter(
    (e) => e.classification!.severity === "FATAL_OR_CRITICAL",
  ).length;
  const mismatchCount = classified.filter(
    (e) => e.classification!.severity !== e.intendedSeverity,
  ).length;

  const meanInferenceMs =
    classifiedCount > 0
      ? classified.reduce((sum, e) => sum + e.classification!.inference_ms, 0) /
        classifiedCount
      : null;

  // Percentages are over the *classified* set, not the total \u2014 a chunk
  // that hasn't been classified yet shouldn't drag the stats down.
  const pct = (n: number) =>
    classifiedCount > 0 ? (n / classifiedCount) * 100 : 0;

  return {
    total,
    classified: classifiedCount,
    errorPct: pct(errorCount),
    fatalPct: pct(fatalCount),
    mismatchPct: pct(mismatchCount),
    meanInferenceMs,
  };
}

interface StatCellProps {
  label: string;
  value: string;
  hint?: string;
  testId: string;
}

function StatCell({ label, value, hint, testId }: StatCellProps) {
  return (
    <Card className="flex-1">
      <CardContent className="p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div
          className="mt-1 font-mono text-2xl font-semibold tabular-nums"
          data-testid={testId}
        >
          {value}
        </div>
        {hint && (
          <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}

export function SummaryStats({ events }: SummaryStatsProps) {
  const stats = useMemo(() => computeStats(events), [events]);

  const fmtPct = (n: number) => `${n.toFixed(1)}%`;
  const fmtMs = (n: number | null) =>
    n === null ? "\u2014" : `${n.toFixed(1)} ms`;

  return (
    <div
      className="grid grid-cols-2 gap-3 md:grid-cols-4"
      data-testid="summary-stats"
    >
      <StatCell
        testId="stat-total"
        label="Chunks"
        value={String(stats.total)}
        hint={
          stats.total === stats.classified
            ? `${stats.classified} classified`
            : `${stats.classified} of ${stats.total} classified`
        }
      />
      <StatCell
        testId="stat-error-pct"
        label="% ERROR"
        value={fmtPct(stats.errorPct)}
      />
      <StatCell
        testId="stat-fatal-pct"
        label="% FATAL"
        value={fmtPct(stats.fatalPct)}
      />
      <StatCell
        testId="stat-mean-ms"
        label="Mean inference"
        value={fmtMs(stats.meanInferenceMs)}
        hint={
          stats.mismatchPct > 0
            ? `${fmtPct(stats.mismatchPct)} intended\u2194predicted mismatch`
            : undefined
        }
      />
    </div>
  );
}
