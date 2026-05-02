/**
 * Tests for <SummaryStats /> and its pure `computeStats` helper.
 *
 * The pure helper carries the bulk of the logic so we test it directly with
 * crafted event arrays. The React shell only verifies that the right values
 * land in the right cells.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SummaryStats, computeStats } from "./summary-stats";
import type { ClassifyResponse, Severity, SimEvent } from "@/lib/types";

function makeClassification(
  severity: Severity,
  inferenceMs = 30,
): ClassifyResponse {
  return {
    severity,
    severity_id:
      severity === "FATAL_OR_CRITICAL"
        ? 0
        : severity === "ERROR"
          ? 1
          : severity === "WARNING"
            ? 2
            : 3,
    confidence: 0.9,
    should_invoke_rca: severity === "FATAL_OR_CRITICAL" || severity === "ERROR",
    priority:
      severity === "FATAL_OR_CRITICAL"
        ? "critical"
        : severity === "ERROR"
          ? "high"
          : severity === "WARNING"
            ? "low"
            : "none",
    inference_ms: inferenceMs,
    all_probabilities: {
      FATAL_OR_CRITICAL: severity === "FATAL_OR_CRITICAL" ? 0.9 : 0.03,
      ERROR: severity === "ERROR" ? 0.9 : 0.03,
      WARNING: severity === "WARNING" ? 0.9 : 0.03,
      NORMAL: severity === "NORMAL" ? 0.9 : 0.03,
    },
  };
}

function makeEvent(
  i: number,
  intended: Severity,
  predicted?: Severity,
  inferenceMs = 30,
): SimEvent {
  return {
    id: `evt-${i}`,
    timestamp: Date.now() - i * 1000,
    intendedSeverity: intended,
    chunkText: `chunk ${i}`,
    numLines: 5,
    classification: predicted ? makeClassification(predicted, inferenceMs) : null,
    classifyError: null,
    status: predicted ? "classified" : "pending",
  };
}

describe("computeStats", () => {
  it("returns zeros for an empty buffer", () => {
    expect(computeStats([])).toEqual({
      total: 0,
      classified: 0,
      errorPct: 0,
      fatalPct: 0,
      mismatchPct: 0,
      meanInferenceMs: null,
    });
  });

  it("computes percentages over the classified subset (not the total)", () => {
    // 2 classified ERROR, 2 classified NORMAL, 1 still pending.
    const events = [
      makeEvent(1, "ERROR", "ERROR", 20),
      makeEvent(2, "ERROR", "ERROR", 40),
      makeEvent(3, "NORMAL", "NORMAL", 60),
      makeEvent(4, "NORMAL", "NORMAL", 80),
      makeEvent(5, "ERROR"), // pending \u2014 must not count
    ];

    const stats = computeStats(events);

    expect(stats.total).toBe(5);
    expect(stats.classified).toBe(4);
    expect(stats.errorPct).toBe(50);
    expect(stats.fatalPct).toBe(0);
    expect(stats.meanInferenceMs).toBe(50); // mean of 20,40,60,80
    expect(stats.mismatchPct).toBe(0);
  });

  it("counts FATAL_OR_CRITICAL toward fatalPct, not errorPct", () => {
    const events = [
      makeEvent(1, "FATAL_OR_CRITICAL", "FATAL_OR_CRITICAL"),
      makeEvent(2, "ERROR", "ERROR"),
    ];
    const stats = computeStats(events);
    expect(stats.fatalPct).toBe(50);
    expect(stats.errorPct).toBe(50);
  });

  it("counts a mismatch when intended != predicted", () => {
    const events = [
      makeEvent(1, "ERROR", "WARNING"), // mismatch
      makeEvent(2, "ERROR", "ERROR"), // match
      makeEvent(3, "NORMAL", "NORMAL"), // match
    ];
    expect(computeStats(events).mismatchPct).toBeCloseTo(33.333, 1);
  });
});

describe("<SummaryStats />", () => {
  it("renders the empty state with zeros and an em-dash for mean ms", () => {
    render(<SummaryStats events={[]} />);
    expect(screen.getByTestId("stat-total")).toHaveTextContent("0");
    expect(screen.getByTestId("stat-error-pct")).toHaveTextContent("0.0%");
    expect(screen.getByTestId("stat-fatal-pct")).toHaveTextContent("0.0%");
    // \u2014 is the em-dash placeholder for "no data yet".
    expect(screen.getByTestId("stat-mean-ms")).toHaveTextContent("\u2014");
  });

  it("renders computed stats for a populated buffer", () => {
    const events = [
      makeEvent(1, "FATAL_OR_CRITICAL", "FATAL_OR_CRITICAL", 25),
      makeEvent(2, "ERROR", "ERROR", 35),
      makeEvent(3, "NORMAL", "NORMAL", 45),
      makeEvent(4, "ERROR", "ERROR", 55),
    ];

    render(<SummaryStats events={events} />);

    expect(screen.getByTestId("stat-total")).toHaveTextContent("4");
    // 2 of 4 classified as ERROR.
    expect(screen.getByTestId("stat-error-pct")).toHaveTextContent("50.0%");
    // 1 of 4 classified as FATAL.
    expect(screen.getByTestId("stat-fatal-pct")).toHaveTextContent("25.0%");
    // mean of 25,35,45,55 = 40 ms.
    expect(screen.getByTestId("stat-mean-ms")).toHaveTextContent("40.0 ms");
  });

  it("surfaces the mismatch hint when intended != predicted on any classified event", () => {
    const events = [
      makeEvent(1, "ERROR", "NORMAL"), // mismatch
      makeEvent(2, "ERROR", "ERROR"),
    ];
    render(<SummaryStats events={events} />);
    expect(screen.getByText(/intended/i)).toHaveTextContent(/mismatch/i);
  });

  it("does NOT show the mismatch hint when everything matches", () => {
    const events = [
      makeEvent(1, "ERROR", "ERROR"),
      makeEvent(2, "NORMAL", "NORMAL"),
    ];
    render(<SummaryStats events={events} />);
    expect(screen.queryByText(/mismatch/i)).not.toBeInTheDocument();
  });
});
