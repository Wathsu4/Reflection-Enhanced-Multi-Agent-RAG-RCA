/**
 * Tests for the experiment detail view. The data + run hooks are mocked,
 * and the heavy ResultsViewer is stubbed, so we only verify wiring:
 * descriptions, the run button calling the runner, planned + busy-elsewhere
 * states, and the load-error path.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Experiment } from "@/lib/api/evaluation";

const useExperimentDetailMock = vi.hoisted(() => vi.fn());
const useExperimentRunMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/hooks/useExperiments", () => ({
  useExperimentDetail: useExperimentDetailMock,
  useExperiments: vi.fn(),
}));
vi.mock("@/lib/hooks/useExperimentRun", () => ({
  useExperimentRun: useExperimentRunMock,
}));
vi.mock("@/components/evaluation/results-viewer", () => ({
  ResultsViewer: () => <div data-testid="results-viewer-mock" />,
}));

import { ExperimentDetailView } from "./experiment-detail-view";

function exp(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: "ablation-no-rag",
    title: "No-RAG ablation",
    summary: "Reason from the raw log alone.",
    description_plain: "Plain words here.",
    description_technical: "Technical words here.",
    rq_tags: ["RQ2"],
    family: "E1.4",
    status: "runnable",
    script: "evaluate",
    base_args: ["--ablation", "no_rag"],
    params: [
      {
        name: "limit",
        label: "Scenario limit",
        kind: "int",
        cli_flag: "--limit",
        default: 0,
        help: "0 = all",
        minimum: 0,
        maximum: 15,
      },
    ],
    outputs_glob: "experiments/results-no_rag-*.json",
    gemini: true,
    gemini_cost_note: "~2 calls/scenario",
    expected_runtime: "~5 min",
    ...overrides,
  };
}

function baseRunner(overrides: Record<string, unknown> = {}) {
  return {
    job: undefined,
    isRunning: false,
    run: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
    startError: null,
    isStarting: false,
    ...overrides,
  };
}

const render_ = () => render(<ExperimentDetailView id="ablation-no-rag" />);

describe("<ExperimentDetailView />", () => {
  beforeEach(() => {
    useExperimentDetailMock.mockReset();
    useExperimentRunMock.mockReset();
    useExperimentRunMock.mockReturnValue(baseRunner());
  });

  it("renders the title and both descriptions across tabs", async () => {
    useExperimentDetailMock.mockReturnValue({
      data: { experiment: exp(), results: [], busy: false, current_job_id: null },
      isLoading: false,
      isError: false,
      error: null,
    });
    render_();
    expect(screen.getByText("No-RAG ablation")).toBeInTheDocument();
    // Plain tab is active by default; Radix only mounts the active tab's
    // content, so the technical copy appears after switching tabs.
    expect(screen.getByTestId("desc-plain")).toHaveTextContent("Plain words here.");
    await userEvent.click(screen.getByTestId("tab-technical"));
    expect(screen.getByTestId("desc-technical")).toHaveTextContent("Technical words here.");
  });

  it("calls runner.run with default params when Run is clicked", async () => {
    const runner = baseRunner();
    useExperimentRunMock.mockReturnValue(runner);
    useExperimentDetailMock.mockReturnValue({
      data: { experiment: exp(), results: [], busy: false, current_job_id: null },
      isLoading: false,
      isError: false,
      error: null,
    });
    render_();
    await userEvent.click(screen.getByTestId("run-button"));
    expect(runner.run).toHaveBeenCalledWith({ limit: 0 });
  });

  it("shows a planned notice and no run button for planned experiments", () => {
    useExperimentDetailMock.mockReturnValue({
      data: {
        experiment: exp({ status: "planned", script: null, params: [] }),
        results: [],
        busy: false,
        current_job_id: null,
      },
      isLoading: false,
      isError: false,
      error: null,
    });
    render_();
    expect(screen.getByTestId("planned-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("run-button")).not.toBeInTheDocument();
  });

  it("warns and disables Run when another experiment is running", () => {
    useExperimentRunMock.mockReturnValue(
      baseRunner({ job: { experiment_id: "other", status: "running" }, isRunning: false }),
    );
    useExperimentDetailMock.mockReturnValue({
      data: { experiment: exp(), results: [], busy: true, current_job_id: "jobX" },
      isLoading: false,
      isError: false,
      error: null,
    });
    render_();
    expect(screen.getByTestId("busy-elsewhere")).toBeInTheDocument();
    expect(screen.getByTestId("run-button")).toBeDisabled();
  });

  it("shows progress for this experiment's own running job", () => {
    useExperimentRunMock.mockReturnValue(
      baseRunner({
        job: {
          experiment_id: "ablation-no-rag",
          status: "running",
          progress: { done: 1, total: 2, phase: "running" },
          log_tail: [],
          result_files: [],
          error: null,
        },
        isRunning: true,
      }),
    );
    useExperimentDetailMock.mockReturnValue({
      data: { experiment: exp(), results: [], busy: true, current_job_id: "self" },
      isLoading: false,
      isError: false,
      error: null,
    });
    render_();
    expect(screen.getByTestId("job-progress")).toBeInTheDocument();
    expect(screen.getByTestId("cancel-button")).toBeInTheDocument();
  });

  it("renders an error when the experiment fails to load", () => {
    useExperimentDetailMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("nope"),
    });
    render_();
    expect(screen.getByTestId("detail-error")).toBeInTheDocument();
  });
});
