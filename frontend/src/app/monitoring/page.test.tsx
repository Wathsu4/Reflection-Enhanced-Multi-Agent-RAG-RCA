/**
 * Smoke test for the monitoring page. We mock the simulator hook so the
 * page test just verifies wiring (Start button \u2192 sim.start, error alert
 * surfaces, etc.). The hook itself is fully exercised in
 * useLogSimulator.test.tsx.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const useLogSimulatorMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/hooks/useLogSimulator", () => ({
  useLogSimulator: useLogSimulatorMock,
  DEFAULT_OPTIONS: {
    profile: "mixed",
    numLines: 10,
    intervalMs: 3_000,
    autoClassify: true,
    maxEvents: 50,
  },
}));

import MonitoringPage from "./page";

const baseSim = () => ({
  events: [],
  latest: null,
  running: false,
  lastError: null,
  options: {
    profile: "mixed" as const,
    numLines: 10,
    intervalMs: 3_000,
    autoClassify: true,
    maxEvents: 50,
  },
  start: vi.fn(),
  stop: vi.fn(),
  clear: vi.fn(),
  updateOptions: vi.fn(),
});

describe("<MonitoringPage />", () => {
  beforeEach(() => {
    useLogSimulatorMock.mockReset();
  });

  it("renders the empty feed and the Start button when stopped", () => {
    useLogSimulatorMock.mockReturnValue(baseSim());

    render(<MonitoringPage />);

    expect(screen.getByTestId("simulator-controls")).toBeInTheDocument();
    expect(screen.getByTestId("event-feed-empty")).toBeInTheDocument();
    expect(screen.getByTestId("latest-event-empty")).toBeInTheDocument();
    expect(screen.getByTestId("start-button")).toBeInTheDocument();
  });

  it("invokes sim.start when the user clicks Start", async () => {
    const sim = baseSim();
    useLogSimulatorMock.mockReturnValue(sim);

    render(<MonitoringPage />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("start-button"));

    expect(sim.start).toHaveBeenCalledTimes(1);
  });

  it("shows the Simulator error alert when lastError is set", () => {
    useLogSimulatorMock.mockReturnValue({
      ...baseSim(),
      lastError: new Error("classifier offline"),
    });

    render(<MonitoringPage />);

    expect(screen.getByText(/simulator hit an error/i)).toBeInTheDocument();
    expect(screen.getByText(/classifier offline/i)).toBeInTheDocument();
  });

  it("renders the latest event in the detail card when one is present", () => {
    const evt = {
      id: "evt-1",
      timestamp: Date.now(),
      intendedSeverity: "FATAL_OR_CRITICAL" as const,
      chunkText: "FATAL kernel panic",
      numLines: 3,
      classification: {
        severity: "FATAL_OR_CRITICAL" as const,
        severity_id: 0 as const,
        confidence: 0.99,
        should_invoke_rca: true,
        priority: "critical" as const,
        inference_ms: 22,
        all_probabilities: {
          FATAL_OR_CRITICAL: 0.99,
          ERROR: 0.005,
          WARNING: 0.003,
          NORMAL: 0.002,
        },
      },
      classifyError: null,
      status: "classified" as const,
    };
    useLogSimulatorMock.mockReturnValue({
      ...baseSim(),
      events: [evt],
      latest: evt,
      running: true,
    });

    render(<MonitoringPage />);

    expect(screen.getByTestId("latest-event-card")).toBeInTheDocument();
    expect(screen.getByTestId("latest-event-chunk")).toHaveTextContent(
      "FATAL kernel panic",
    );
    expect(screen.getByTestId("investigate-button")).toBeInTheDocument();
  });
});
