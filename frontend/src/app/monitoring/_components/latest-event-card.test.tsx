/**
 * Tests for <LatestEventCard />. Verifies the three render branches
 * (empty / pending / classified / error) and the RCA button gating.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { LatestEventCard } from "./latest-event-card";
import type { SimEvent } from "@/lib/types";

function makeEvent(overrides: Partial<SimEvent> = {}): SimEvent {
  return {
    id: "evt-1",
    timestamp: Date.now(),
    intendedSeverity: "ERROR",
    chunkText: "2024-01-01 ERROR something broke\n2024-01-01 ERROR retry failed",
    numLines: 2,
    classification: null,
    classifyError: null,
    status: "pending",
    ...overrides,
  };
}

describe("<LatestEventCard />", () => {
  it("shows an empty state when no event is selected", () => {
    render(<LatestEventCard event={null} />);
    expect(screen.getByTestId("latest-event-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("latest-event-card")).not.toBeInTheDocument();
  });

  it("renders the chunk text and shows 'Awaiting' while pending", () => {
    render(<LatestEventCard event={makeEvent()} />);
    expect(screen.getByText(/awaiting classification/i)).toBeInTheDocument();
    expect(screen.getByTestId("latest-event-chunk")).toHaveTextContent(
      "ERROR something broke",
    );
  });

  it("shows the classification details when status is 'classified'", () => {
    render(
      <LatestEventCard
        event={makeEvent({
          status: "classified",
          classification: {
            severity: "FATAL_OR_CRITICAL",
            severity_id: 0,
            confidence: 0.97,
            should_invoke_rca: true,
            priority: "critical",
            inference_ms: 41.2,
            all_probabilities: {
              FATAL_OR_CRITICAL: 0.97,
              ERROR: 0.02,
              WARNING: 0.005,
              NORMAL: 0.005,
            },
          },
        })}
      />,
    );

    expect(screen.getByText(/latest classification/i)).toBeInTheDocument();
    // Confidence header shows the formatted percentage. It also appears in
    // the probability row for FATAL_OR_CRITICAL, hence getAllByText.
    expect(screen.getAllByText("97.0%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/41\.2 ms/)).toBeInTheDocument();
    // "Investigate with RCA" is enabled when should_invoke_rca is true.
    expect(screen.getByTestId("investigate-button")).not.toBeDisabled();
    expect(screen.getByTestId("investigate-button")).toHaveTextContent(
      /investigate with rca/i,
    );
  });

  it("disables the Investigate button when should_invoke_rca is false", () => {
    render(
      <LatestEventCard
        event={makeEvent({
          status: "classified",
          classification: {
            severity: "NORMAL",
            severity_id: 3,
            confidence: 0.99,
            should_invoke_rca: false,
            priority: "none",
            inference_ms: 18,
            all_probabilities: {
              FATAL_OR_CRITICAL: 0,
              ERROR: 0,
              WARNING: 0.01,
              NORMAL: 0.99,
            },
          },
        })}
      />,
    );

    expect(screen.getByTestId("investigate-button")).toBeDisabled();
    expect(screen.getByTestId("investigate-button")).toHaveTextContent(
      /rca not warranted/i,
    );
  });

  it("renders the error state when classification failed", () => {
    render(
      <LatestEventCard
        event={makeEvent({
          status: "error",
          classifyError: "Cannot reach classifier service",
        })}
      />,
    );

    expect(
      screen.getByText(/cannot reach classifier service/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("investigate-button")).not.toBeInTheDocument();
  });
});
