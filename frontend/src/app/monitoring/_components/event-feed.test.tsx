/**
 * Tests for <EventFeed />. Asserts:
 *  - empty state copy
 *  - rows appear with the right severity, status indicators, and selection
 *  - clicking a row calls onSelect
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { EventFeed } from "./event-feed";
import type { SimEvent } from "@/lib/types";

function makeEvent(overrides: Partial<SimEvent> = {}): SimEvent {
  return {
    id: "evt-1",
    timestamp: Date.now(),
    intendedSeverity: "ERROR",
    chunkText: "ERROR ...",
    numLines: 5,
    classification: null,
    classifyError: null,
    status: "pending",
    ...overrides,
  };
}

const classified: SimEvent = makeEvent({
  id: "evt-classified",
  status: "classified",
  classification: {
    severity: "FATAL_OR_CRITICAL",
    severity_id: 0,
    confidence: 0.97,
    should_invoke_rca: true,
    priority: "critical",
    inference_ms: 41,
    all_probabilities: {
      FATAL_OR_CRITICAL: 0.97,
      ERROR: 0.02,
      WARNING: 0.005,
      NORMAL: 0.005,
    },
  },
});

const errored: SimEvent = makeEvent({
  id: "evt-error",
  status: "error",
  classifyError: "classifier offline",
});

describe("<EventFeed />", () => {
  it("renders the empty state when there are no events", () => {
    render(<EventFeed events={[]} />);
    expect(screen.getByTestId("event-feed-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("event-feed-list")).not.toBeInTheDocument();
  });

  it("renders one row per event with the correct status attribute", () => {
    render(<EventFeed events={[makeEvent(), classified, errored]} />);

    const rows = screen.getAllByTestId("event-feed-row");
    expect(rows).toHaveLength(3);
    expect(rows[0]!.getAttribute("data-status")).toBe("pending");
    expect(rows[1]!.getAttribute("data-status")).toBe("classified");
    expect(rows[2]!.getAttribute("data-status")).toBe("error");
  });

  it("uses the classified severity (not the intended one) when available", () => {
    render(<EventFeed events={[classified]} />);
    // The badge should display the classified severity (FATAL_OR_CRITICAL),
    // not the intended one (ERROR).
    expect(screen.getByText(/FATAL OR CRITICAL/)).toBeInTheDocument();
  });

  it("shows the classify error message inline for errored rows", () => {
    render(<EventFeed events={[errored]} />);
    expect(screen.getByText(/classifier offline/i)).toBeInTheDocument();
  });

  it("highlights the selected row and calls onSelect on click", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const events = [makeEvent({ id: "a" }), makeEvent({ id: "b" })];

    render(<EventFeed events={events} selectedId="a" onSelect={onSelect} />);

    const rows = screen.getAllByTestId("event-feed-row");
    expect(rows[0]!.getAttribute("data-selected")).toBe("true");
    expect(rows[1]!.getAttribute("data-selected")).toBe("false");

    await user.click(rows[1]!);
    expect(onSelect).toHaveBeenCalledWith(events[1]);
  });

  it("shows the mismatch indicator only when classified severity differs from intended", () => {
    const matched: SimEvent = makeEvent({
      id: "evt-match",
      intendedSeverity: "ERROR",
      status: "classified",
      classification: {
        severity: "ERROR",
        severity_id: 1,
        confidence: 0.9,
        should_invoke_rca: true,
        priority: "high",
        inference_ms: 30,
        all_probabilities: {
          FATAL_OR_CRITICAL: 0.05,
          ERROR: 0.9,
          WARNING: 0.03,
          NORMAL: 0.02,
        },
      },
    });
    const mismatched: SimEvent = makeEvent({
      id: "evt-mismatch",
      intendedSeverity: "ERROR",
      status: "classified",
      classification: {
        severity: "WARNING",
        severity_id: 2,
        confidence: 0.7,
        should_invoke_rca: false,
        priority: "low",
        inference_ms: 30,
        all_probabilities: {
          FATAL_OR_CRITICAL: 0.05,
          ERROR: 0.2,
          WARNING: 0.7,
          NORMAL: 0.05,
        },
      },
    });

    render(<EventFeed events={[matched, mismatched]} />);

    const rows = screen.getAllByTestId("event-feed-row");
    expect(rows[0]!.getAttribute("data-mismatch")).toBe("false");
    expect(rows[1]!.getAttribute("data-mismatch")).toBe("true");

    // Exactly one mismatch icon visible across the feed.
    expect(screen.getAllByTestId("mismatch-indicator")).toHaveLength(1);
  });

  it("does not show the mismatch indicator on pending events", () => {
    render(<EventFeed events={[makeEvent({ status: "pending" })]} />);
    expect(screen.queryByTestId("mismatch-indicator")).not.toBeInTheDocument();
  });
});
