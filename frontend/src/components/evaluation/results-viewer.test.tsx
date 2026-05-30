/**
 * Tests for the results viewer. `useEvalResult` is mocked so we can feed
 * canned JSON / markdown payloads and assert the structured renderers and
 * history list behave.
 */
import type { ReactElement } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { ResultEntry } from "@/lib/api/evaluation";

const useEvalResultMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/hooks/useEvalResult", () => ({
  useEvalResult: useEvalResultMock,
}));

import { ResultsViewer } from "./results-viewer";

// Metric labels use Radix tooltips, which require a TooltipProvider
// ancestor (supplied app-wide by the root layout in production).
const renderRV = (ui: ReactElement) =>
  render(<TooltipProvider>{ui}</TooltipProvider>);

const JSON_RESULT = JSON.stringify({
  summary: {
    n: 2,
    ablation: "no_rag",
    keyword_verdict_counts: { exact: 1, partial: 0, miss: 1 },
    keyword_accuracy_exact_or_partial: 0.5,
    expected_incident_retrieval_recall: 1.0,
    retrieval_ir: { recall_at_k: 1.0, mrr: 1.0, ndcg_at_k: 1.0, k: 5, n_scored: 2 },
    mean_latency_s: 0.11,
    mean_total_tokens: 1234,
    mean_top_retrieval_similarity: 0.75,
  },
  results: [
    {
      id: "redis-1",
      keyword_verdict: "exact",
      keyword_score: 0.8,
      top_retrieval_similarity: 0.82,
      expected_incident_rank: 1,
      latency_s: 0.18,
      total_tokens: 600,
    },
  ],
});

function entry(overrides: Partial<ResultEntry> = {}): ResultEntry {
  return {
    timestamp_ts: 1_700_000_000,
    size_bytes: 100,
    json_path: "experiments/results-no_rag-1.json",
    markdown_path: "experiments/results-no_rag-1.md",
    ...overrides,
  };
}

describe("<ResultsViewer />", () => {
  beforeEach(() => useEvalResultMock.mockReset());

  it("shows an empty state when there are no results", () => {
    useEvalResultMock.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderRV(<ResultsViewer results={[]} />);
    expect(screen.getByTestId("no-results")).toBeInTheDocument();
  });

  it("renders the structured summary + scenario table for a JSON result", () => {
    useEvalResultMock.mockReturnValue({
      data: { path: "experiments/results-no_rag-1.json", format: "json", content: JSON_RESULT },
      isLoading: false,
      isError: false,
    });
    renderRV(<ResultsViewer results={[entry()]} />);
    expect(screen.getByTestId("result-summary")).toBeInTheDocument();
    expect(screen.getByTestId("scenario-table")).toBeInTheDocument();
    expect(screen.getByText("redis-1")).toBeInTheDocument();
    // IR metric surfaced.
    expect(screen.getByText("Recall@5")).toBeInTheDocument();
  });

  it("renders markdown for a markdown-only result", () => {
    useEvalResultMock.mockReturnValue({
      data: { path: "memory-evolution-1.md", format: "markdown", content: "# Drift\n\n- a" },
      isLoading: false,
      isError: false,
    });
    renderRV(
      <ResultsViewer
        results={[entry({ json_path: null, markdown_path: "memory-evolution-1.md" })]}
      />,
    );
    expect(screen.getByTestId("markdown-view")).toBeInTheDocument();
  });

  it("lists run history and lets you switch between runs", async () => {
    useEvalResultMock.mockReturnValue({
      data: { path: "x", format: "json", content: JSON_RESULT },
      isLoading: false,
      isError: false,
    });
    renderRV(
      <ResultsViewer
        results={[
          entry({ timestamp_ts: 1_700_000_500, json_path: "experiments/results-no_rag-2.json", markdown_path: null }),
          entry({ timestamp_ts: 1_700_000_000, json_path: "experiments/results-no_rag-1.json", markdown_path: null }),
        ]}
      />,
    );
    const items = screen.getAllByTestId("result-history-item");
    expect(items).toHaveLength(2);
    await userEvent.click(items[1]);
    // After clicking, the hook is asked for the older file.
    expect(useEvalResultMock).toHaveBeenCalledWith("experiments/results-no_rag-1.json");
  });
});
