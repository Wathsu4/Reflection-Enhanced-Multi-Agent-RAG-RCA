"use client";

/**
 * The body of the experiment detail page, taking a plain `id`.
 *
 * Kept separate from the route's `page.tsx` (which unwraps the Next 16
 * `params` Promise via `use()`) so this UI is straightforward to unit
 * test with a string id.
 *
 * Shows what the experiment evaluates (plain-English + technical tabs),
 * a parameter form, a run/cancel control, live polled progress, and the
 * results + history (via <ResultsViewer/>).
 */

import { ArrowLeft, Ban, Loader2, Play } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { RqBadges } from "@/components/evaluation/experiment-card";
import { JobProgress } from "@/components/evaluation/job-progress";
import { ParamsForm, defaultParamValues, type ParamValues } from "@/components/evaluation/params-form";
import { ResultsViewer } from "@/components/evaluation/results-viewer";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useExperimentDetail } from "@/lib/hooks/useExperiments";
import { useExperimentRun } from "@/lib/hooks/useExperimentRun";

export function ExperimentDetailView({ id }: { id: string }) {
  const detailQuery = useExperimentDetail(id);
  const detail = detailQuery.data;
  const experiment = detail?.experiment;

  const adoptJobId = detail?.busy ? detail.current_job_id : null;
  const runner = useExperimentRun(id, { adoptJobId });

  // Local form state, seeded from the param defaults once the schema loads.
  const [values, setValues] = useState<ParamValues | null>(null);
  const effectiveValues = useMemo<ParamValues>(
    () => values ?? (experiment ? defaultParamValues(experiment.params) : {}),
    [values, experiment],
  );

  if (detailQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading experiment…
      </div>
    );
  }

  if (detailQuery.isError || !experiment) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <Alert variant="destructive" data-testid="detail-error">
          <AlertTitle>Couldn&apos;t load this experiment</AlertTitle>
          <AlertDescription>
            {(detailQuery.error as Error)?.message ??
              "Unknown experiment, or the agent service is offline."}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const ownsJob = runner.job?.experiment_id === id;
  const showProgress = Boolean(runner.job && ownsJob);
  const busyElsewhere = Boolean(detail?.busy) && !ownsJob;
  const planned = experiment.status === "planned";
  const runDisabled = planned || runner.isRunning || runner.isStarting || busyElsewhere;

  return (
    <div className="flex flex-1 flex-col gap-6">
      <BackLink />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex flex-col gap-2">
              <CardTitle className="flex items-center gap-2">
                {experiment.title}
                {planned && <Badge variant="outline">Planned</Badge>}
              </CardTitle>
              <CardDescription>{experiment.summary}</CardDescription>
              <div className="flex flex-wrap items-center gap-2">
                <RqBadges tags={experiment.rq_tags} />
                {experiment.family && (
                  <span className="font-mono text-xs text-muted-foreground">
                    {experiment.family}
                  </span>
                )}
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* What this evaluates */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">What this evaluates</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="plain">
            <TabsList>
              <TabsTrigger value="plain" data-testid="tab-plain">
                Plain English
              </TabsTrigger>
              <TabsTrigger value="technical" data-testid="tab-technical">
                Technical
              </TabsTrigger>
            </TabsList>
            <TabsContent value="plain">
              <p className="text-sm leading-relaxed" data-testid="desc-plain">
                {experiment.description_plain}
              </p>
            </TabsContent>
            <TabsContent value="technical">
              <p className="text-sm leading-relaxed" data-testid="desc-technical">
                {experiment.description_technical}
              </p>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Run */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Run</CardTitle>
          <CardDescription className="flex flex-wrap gap-x-3 gap-y-1">
            <span>
              {experiment.gemini_cost_note ||
                (experiment.gemini ? "Uses Gemini." : "No Gemini calls.")}
            </span>
            {experiment.expected_runtime && (
              <span>Expected: {experiment.expected_runtime}</span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {planned ? (
            <Alert data-testid="planned-notice">
              <AlertTitle>Not implemented yet</AlertTitle>
              <AlertDescription>
                This experiment is described for completeness but isn&apos;t
                runnable from the console yet.
              </AlertDescription>
            </Alert>
          ) : (
            <>
              <ParamsForm
                params={experiment.params}
                values={effectiveValues}
                onChange={setValues}
                disabled={runDisabled}
              />

              {busyElsewhere && (
                <Alert data-testid="busy-elsewhere">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <AlertTitle>Another evaluation is running</AlertTitle>
                  <AlertDescription>
                    Only one run executes at a time. Wait for it to finish, then
                    try again.
                  </AlertDescription>
                </Alert>
              )}

              {runner.startError && (
                <Alert variant="destructive" data-testid="start-error">
                  <AlertTitle>Could not start the run</AlertTitle>
                  <AlertDescription>{runner.startError.message}</AlertDescription>
                </Alert>
              )}

              <div className="flex items-center gap-2">
                <Button
                  data-testid="run-button"
                  disabled={runDisabled}
                  onClick={() => runner.run(effectiveValues)}
                  className="gap-1"
                >
                  {runner.isRunning || runner.isStarting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {runner.isRunning ? "Running…" : "Run experiment"}
                </Button>
                {runner.isRunning && ownsJob && (
                  <Button
                    data-testid="cancel-button"
                    variant="outline"
                    onClick={runner.cancel}
                    className="gap-1"
                  >
                    <Ban className="h-4 w-4" /> Cancel
                  </Button>
                )}
              </div>

              {showProgress && runner.job && <JobProgress job={runner.job} />}
            </>
          )}
        </CardContent>
      </Card>

      {/* Results + history */}
      <ResultsViewer
        results={detail?.results ?? []}
        latestJob={ownsJob ? runner.job : undefined}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/evaluation"
      className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      data-testid="back-link"
    >
      <ArrowLeft className="h-4 w-4" /> All experiments
    </Link>
  );
}
