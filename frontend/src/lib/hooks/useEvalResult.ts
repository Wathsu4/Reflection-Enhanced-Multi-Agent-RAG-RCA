"use client";

import { useQuery } from "@tanstack/react-query";

import { getResult, type ResultFileResponse } from "@/lib/api/evaluation";

/**
 * Fetches a single evaluation result file (markdown or JSON) by its path
 * relative to `eval/`. Cached aggressively -- result files are immutable
 * once written.
 */
export function useEvalResult(relPath: string | null | undefined) {
  return useQuery<ResultFileResponse>({
    queryKey: ["eval", "result", relPath],
    queryFn: ({ signal }) => getResult(relPath as string, signal),
    enabled: Boolean(relPath),
    staleTime: Infinity,
    retry: 1,
  });
}
