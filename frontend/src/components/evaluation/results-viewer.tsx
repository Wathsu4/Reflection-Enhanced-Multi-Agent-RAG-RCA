"use client";

import { FileText, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MarkdownView } from "@/components/agents/MarkdownView";
import { MetricLabel } from "@/components/evaluation/metric-label";
import { Badge } from "@/components/ui/badge";
import type { MetricKey } from "@/lib/eval/metric-info";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useEvalResult } from "@/lib/hooks/useEvalResult";
import type { Job, ResultEntry } from "@/lib/api/evaluation";

// -------------------- parsed-JSON shapes (subset we render) --------------------

interface IRMetrics {
  recall_at_k: number | null;
  mrr: number | null;
  ndcg_at_k: number | null;
  k: number;
  n_scored: number;
}

interface ResultSummary {
  n: number;
  ablation?: string;
  keyword_verdict_counts?: { exact: number; partial: number; miss: number };
  keyword_accuracy_exact_or_partial?: number;
  expected_incident_retrieval_recall?: number | null;
  retrieval_ir?: IRMetrics | null;
  mean_latency_s?: number | null;
  p95_latency_s?: number | null;
  mean_total_tokens?: number | null;
  mean_top_retrieval_similarity?: number | null;
  llm_judge_verdict_counts?: Record<string, number> | null;
}

interface ScenarioRow {
  id: string;
  keyword_verdict?: string;
  keyword_score?: number;
  top_retrieval_similarity?: number | null;
  expected_incident_rank?: number | null;
  expected_incident_id?: string | null;
  latency_s?: number;
  total_tokens?: number;
  llm_judge_verdict?: string | null;
  error?: string | null;
}

interface ParsedResultFile {
  summary: ResultSummary;
  results: ScenarioRow[];
}

// -------------------- small presentational bits --------------------

function Metric({
  label,
  value,
  metricKey,
}: {
  label: string;
  value: React.ReactNode;
  metricKey?: MetricKey;
}) {
  return (
    <div className="rounded border bg-muted/30 p-2">
      <div className="text-[11px] text-muted-foreground">
        {metricKey ? (
          <MetricLabel metricKey={metricKey}>{label}</MetricLabel>
        ) : (
          label
        )}
      </div>
      <div className="font-mono text-sm">{value}</div>
    </div>
  );
}

function fmt(v: number | null | undefined, digits = 3): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

export function ResultSummaryGrid({ summary }: { summary: ResultSummary }) {
  const vc = summary.keyword_verdict_counts;
  const ir = summary.retrieval_ir;
  return (
    <div
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4"
      data-testid="result-summary"
    >
      <Metric label="Scenarios" metricKey="scenarios" value={summary.n} />
      <Metric
        label="Keyword acc (exact+partial)"
        metricKey="keyword_acc"
        value={fmt(summary.keyword_accuracy_exact_or_partial, 2)}
      />
      {vc && (
        <Metric
          label="Verdicts (E/P/M)"
          metricKey="keyword_verdict"
          value={`${vc.exact}/${vc.partial}/${vc.miss}`}
        />
      )}
      {summary.expected_incident_retrieval_recall !== undefined && (
        <Metric
          label="Retrieval recall"
          metricKey="retrieval_recall"
          value={fmt(summary.expected_incident_retrieval_recall, 2)}
        />
      )}
      {ir && ir.recall_at_k !== null && (
        <>
          <Metric label={`Recall@${ir.k}`} metricKey="recall_at_k" value={fmt(ir.recall_at_k, 2)} />
          <Metric label="MRR" metricKey="mrr" value={fmt(ir.mrr, 2)} />
          <Metric label={`nDCG@${ir.k}`} metricKey="ndcg" value={fmt(ir.ndcg_at_k, 2)} />
        </>
      )}
      <Metric label="Mean latency (s)" metricKey="mean_latency" value={fmt(summary.mean_latency_s, 2)} />
      {summary.mean_total_tokens != null && (
        <Metric label="Mean tokens" metricKey="mean_tokens" value={fmt(summary.mean_total_tokens, 0)} />
      )}
      {summary.mean_top_retrieval_similarity != null && (
        <Metric
          label="Mean top sim"
          metricKey="mean_top_sim"
          value={fmt(summary.mean_top_retrieval_similarity, 3)}
        />
      )}
    </div>
  );
}

export function ScenarioTable({ rows }: { rows: ScenarioRow[] }) {
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto" data-testid="scenario-table">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="px-2 py-1"><MetricLabel metricKey="scenario_id">id</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="keyword_verdict">verdict</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="keyword_score">kw</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="top_sim">top sim</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="expected_rank">rank</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="latency">latency</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="tokens">tokens</MetricLabel></th>
            <th className="px-2 py-1"><MetricLabel metricKey="llm_judge">judge</MetricLabel></th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {rows.map((r) => (
            <tr key={r.id} className="border-b last:border-0">
              <td className="px-2 py-1">{r.id}</td>
              <td className="px-2 py-1">{r.keyword_verdict ?? "—"}</td>
              <td className="px-2 py-1">{fmt(r.keyword_score, 2)}</td>
              <td className="px-2 py-1">{fmt(r.top_retrieval_similarity, 3)}</td>
              <td className="px-2 py-1">{r.expected_incident_rank ?? "—"}</td>
              <td className="px-2 py-1">{fmt(r.latency_s, 2)}</td>
              <td className="px-2 py-1">{r.total_tokens || "—"}</td>
              <td className="px-2 py-1">{r.llm_judge_verdict ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

// -------------------- renders one selected result --------------------

function ResultBody({ relPath }: { relPath: string }) {
  const { data, isLoading, isError, error } = useEvalResult(relPath);

  if (isLoading) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted-foreground"
        data-testid="result-loading"
      >
        <Loader2 className="h-4 w-4 animate-spin" /> Loading result…
      </div>
    );
  }
  if (isError || !data) {
    return (
      <p className="text-sm text-destructive" data-testid="result-error">
        {(error as Error)?.message ?? "Could not load this result."}
      </p>
    );
  }

  if (data.format === "json") {
    try {
      const parsed = JSON.parse(data.content) as ParsedResultFile;
      return (
        <div className="flex flex-col gap-4">
          <ResultSummaryGrid summary={parsed.summary} />
          <ScenarioTable rows={parsed.results ?? []} />
        </div>
      );
    } catch {
      return (
        <p className="text-sm text-destructive">Result JSON was unparseable.</p>
      );
    }
  }
  return <MarkdownView markdown={data.content} />;
}

// -------------------- the viewer --------------------

/**
 * Shows the result history for an experiment and renders the selected one:
 * structured metrics + per-scenario table for JSON pipeline results, or the
 * markdown report for memory-evolution. Selecting a row loads it on demand.
 */
export function ResultsViewer({
  results,
  latestJob,
}: {
  results: ResultEntry[];
  latestJob?: Job;
}) {
  // Prefer the freshly-finished job's primary file; else the newest history
  // entry. JSON (structured) is preferred over markdown when both exist.
  const preferredFromJob = useMemo<string | null>(() => {
    if (!latestJob || latestJob.status !== "succeeded") return null;
    const files = latestJob.result_files ?? [];
    return files.find((f) => f.endsWith(".json")) ?? files[0] ?? null;
  }, [latestJob]);

  const newestFromHistory =
    results[0]?.json_path ?? results[0]?.markdown_path ?? null;

  const [selected, setSelected] = useState<string | null>(null);
  const effectiveSelected = selected ?? preferredFromJob ?? newestFromHistory;

  // When a run finishes, jump to its result automatically.
  useEffect(() => {
    if (preferredFromJob) setSelected(preferredFromJob);
  }, [preferredFromJob]);

  return (
    <Card data-testid="results-viewer">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Results</CardTitle>
        <CardDescription>
          {results.length === 0
            ? "No runs recorded yet. Run the experiment to produce a result."
            : `${results.length} past run${results.length === 1 ? "" : "s"}.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {results.length > 0 && (
          <div className="flex flex-wrap gap-2" data-testid="results-history">
            {results.map((r) => {
              const path = r.json_path ?? r.markdown_path ?? "";
              const active = path === effectiveSelected;
              return (
                <Button
                  key={path}
                  data-testid="result-history-item"
                  variant={active ? "default" : "outline"}
                  size="sm"
                  className="gap-1"
                  onClick={() => setSelected(path)}
                >
                  <FileText className="h-3 w-3" />
                  {formatTs(r.timestamp_ts)}
                  {r.json_path && !r.markdown_path && (
                    <Badge variant="secondary" className="ml-1 text-[10px]">
                      json
                    </Badge>
                  )}
                </Button>
              );
            })}
          </div>
        )}

        {effectiveSelected ? (
          <ResultBody relPath={effectiveSelected} />
        ) : (
          <p className="text-sm text-muted-foreground" data-testid="no-results">
            Nothing to show yet.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
