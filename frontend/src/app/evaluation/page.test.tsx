/**
 * Smoke test for the evaluation landing page. The data hook is mocked so
 * we only verify wiring: grouping into Available/Planned, the busy banner,
 * loading + error states.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const useExperimentsMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/hooks/useExperiments", () => ({
  useExperiments: useExperimentsMock,
}));

import EvaluationPage from "./page";
import type { Experiment } from "@/lib/api/evaluation";

function exp(overrides: Partial<Experiment>): Experiment {
  return {
    id: "x",
    title: "Title",
    summary: "Summary",
    description_plain: "",
    description_technical: "",
    rq_tags: ["RQ1"],
    family: "E1.1",
    status: "runnable",
    script: "evaluate",
    base_args: [],
    params: [],
    outputs_glob: "results-*.json",
    gemini: true,
    gemini_cost_note: "",
    expected_runtime: "~5 min",
    ...overrides,
  };
}

describe("<EvaluationPage />", () => {
  beforeEach(() => useExperimentsMock.mockReset());

  it("groups experiments into available and planned", () => {
    useExperimentsMock.mockReturnValue({
      data: {
        experiments: [
          exp({ id: "run-1", title: "Runnable one", status: "runnable" }),
          exp({ id: "plan-1", title: "Planned one", status: "planned" }),
        ],
        busy: false,
        current_job_id: null,
      },
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<EvaluationPage />);

    expect(screen.getByText(/Available now \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Planned \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("Runnable one")).toBeInTheDocument();
    expect(screen.getByText("Planned one")).toBeInTheDocument();
    // Runnable card is a link; planned card is not.
    expect(screen.getAllByTestId("experiment-card-link")).toHaveLength(1);
  });

  it("shows the busy banner when a job is running", () => {
    useExperimentsMock.mockReturnValue({
      data: { experiments: [], busy: true, current_job_id: "job1" },
      isLoading: false,
      isError: false,
      error: null,
    });
    render(<EvaluationPage />);
    expect(screen.getByTestId("busy-banner")).toBeInTheDocument();
  });

  it("renders a loading indicator", () => {
    useExperimentsMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    });
    render(<EvaluationPage />);
    expect(screen.getByTestId("experiments-loading")).toBeInTheDocument();
  });

  it("renders an error alert", () => {
    useExperimentsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("offline"),
    });
    render(<EvaluationPage />);
    expect(screen.getByTestId("experiments-error")).toBeInTheDocument();
  });
});
