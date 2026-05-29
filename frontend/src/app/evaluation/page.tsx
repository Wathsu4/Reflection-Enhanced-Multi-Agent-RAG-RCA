"use client";

/**
 * Evaluation console — landing page.
 *
 * Renders one card per experiment from the backend registry
 * (`/eval/experiments`), grouped into "Available now" (implemented +
 * runnable) and "Planned" (described but not yet built). Each available
 * card links to its detail page where it can be re-run.
 */

import { FlaskConical, Loader2 } from "lucide-react";

import { ExperimentCard } from "@/components/evaluation/experiment-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useExperiments } from "@/lib/hooks/useExperiments";
import type { Experiment } from "@/lib/api/evaluation";

function ExperimentGrid({ experiments }: { experiments: Experiment[] }) {
  return (
    <div
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      data-testid="experiment-grid"
    >
      {experiments.map((e) => (
        <ExperimentCard key={e.id} experiment={e} />
      ))}
    </div>
  );
}

export default function EvaluationPage() {
  const { data, isLoading, isError, error } = useExperiments();

  const experiments = data?.experiments ?? [];
  const runnable = experiments.filter((e) => e.status === "runnable");
  const planned = experiments.filter((e) => e.status === "planned");

  return (
    <div className="flex flex-1 flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5" />
            Evaluation console
          </CardTitle>
          <CardDescription>
            Re-runnable, self-describing experiments that back the thesis
            claims. Each experiment explains what it measures in plain and
            technical terms, runs in an isolated sandbox (your live demo
            memory is never touched), and renders its own results.
          </CardDescription>
        </CardHeader>
        {data?.busy && (
          <CardContent>
            <Alert data-testid="busy-banner">
              <Loader2 className="h-4 w-4 animate-spin" />
              <AlertTitle>An evaluation is currently running</AlertTitle>
              <AlertDescription>
                Only one run executes at a time. Open the running experiment to
                watch its progress.
              </AlertDescription>
            </Alert>
          </CardContent>
        )}
      </Card>

      {isLoading && (
        <div
          className="flex items-center gap-2 text-sm text-muted-foreground"
          data-testid="experiments-loading"
        >
          <Loader2 className="h-4 w-4 animate-spin" /> Loading experiments…
        </div>
      )}

      {isError && (
        <Alert variant="destructive" data-testid="experiments-error">
          <AlertTitle>Couldn&apos;t load experiments</AlertTitle>
          <AlertDescription>
            {(error as Error)?.message ??
              "The agent service may be offline. Start it and retry."}
          </AlertDescription>
        </Alert>
      )}

      {runnable.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Available now ({runnable.length})
          </h2>
          <ExperimentGrid experiments={runnable} />
        </section>
      )}

      {planned.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Planned ({planned.length})
          </h2>
          <ExperimentGrid experiments={planned} />
        </section>
      )}
    </div>
  );
}
