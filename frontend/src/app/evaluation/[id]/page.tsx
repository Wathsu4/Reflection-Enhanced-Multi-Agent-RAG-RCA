"use client";

/**
 * Evaluation experiment detail route.
 *
 * In Next 16 `params` is a Promise, so this client component unwraps it
 * with React's `use()` and delegates the actual UI to
 * <ExperimentDetailView/> (which takes a plain id and is unit-tested
 * directly).
 */

import { use } from "react";

import { ExperimentDetailView } from "@/components/evaluation/experiment-detail-view";

export default function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <ExperimentDetailView id={id} />;
}
