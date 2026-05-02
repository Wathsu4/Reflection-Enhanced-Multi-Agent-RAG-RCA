/**
 * Tests for InvestigationsPanel. Pure presentational; we feed it a
 * hand-crafted Investigation list and assert what the user sees.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { InvestigationsPanel } from "@/app/monitoring/_components/investigations-panel";
import type { Investigation, Severity } from "@/lib/types";

function makeInv(
  partial: Partial<Investigation> & { id: string },
): Investigation {
  return {
    triggeredBy: "sim-evt-1",
    startedAt: 1000,
    completedAt: 4500,
    status: "done",
    events: [],
    chunk: "ERROR Foo",
    severity: "ERROR" as Severity,
    finalAnswer: "## Root cause\nFirewall blocked Redis port 6379.",
    error: null,
    ...partial,
  };
}

describe("InvestigationsPanel: empty state", () => {
  it("shows a hint when there are no investigations and auto-RCA is on", () => {
    render(<InvestigationsPanel investigations={[]} autoRcaEnabled={true} />);
    expect(screen.getByText(/automatically/i)).toBeInTheDocument();
  });

  it("explains that auto-RCA is OFF when the toggle is disabled", () => {
    render(<InvestigationsPanel investigations={[]} autoRcaEnabled={false} />);
    expect(screen.getByText(/auto-rca is currently off/i)).toBeInTheDocument();
  });
});

describe("InvestigationsPanel: list rendering", () => {
  it("renders one card per investigation in input order (newest-first)", () => {
    render(
      <InvestigationsPanel
        autoRcaEnabled={true}
        investigations={[
          makeInv({ id: "i-1" }),
          makeInv({ id: "i-2", status: "running", finalAnswer: null }),
        ]}
      />,
    );
    const cards = screen.getAllByTestId("investigation-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("data-status", "done");
    expect(cards[1]).toHaveAttribute("data-status", "running");
  });

  it("shows the root-cause preview in the collapsed header", () => {
    render(
      <InvestigationsPanel
        autoRcaEnabled={true}
        investigations={[
          makeInv({
            id: "i-1",
            finalAnswer:
              "## Root cause\nFirewall change blocked Redis port 6379.",
          }),
        ]}
      />,
    );
    const previews = screen.getAllByTestId("root-cause-preview");
    expect(previews[0].textContent).toMatch(/firewall/i);
  });

  it("formats the duration in seconds when > 1s", () => {
    render(
      <InvestigationsPanel
        autoRcaEnabled={true}
        investigations={[
          makeInv({ id: "i-1", startedAt: 1000, completedAt: 7400 }),
        ]}
      />,
    );
    expect(screen.getByText(/6\.4s/)).toBeInTheDocument();
  });

  it("renders 'queued…' for a queued investigation", () => {
    render(
      <InvestigationsPanel
        autoRcaEnabled={true}
        investigations={[
          makeInv({
            id: "q-1",
            status: "queued",
            completedAt: null,
            finalAnswer: null,
          }),
        ]}
      />,
    );
    // The string "queued" appears in both the status badge and the
    // duration label, so allow >=1 match rather than insisting on
    // exactly one.
    expect(screen.getAllByText(/queued/).length).toBeGreaterThan(0);
    expect(screen.getByText(/waiting in queue/i)).toBeInTheDocument();
  });

  it("renders error badge + message for errored investigations", () => {
    render(
      <InvestigationsPanel
        autoRcaEnabled={true}
        investigations={[
          makeInv({
            id: "e-1",
            status: "error",
            finalAnswer: null,
            error: "Agent service error (500)",
          }),
        ]}
      />,
    );
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getAllByText(/agent service error/i).length).toBeGreaterThan(0);
  });
});

describe("InvestigationsPanel: expand/collapse", () => {
  it("does not render the agent timeline until expanded", async () => {
    const user = userEvent.setup();
    render(
      <InvestigationsPanel
        autoRcaEnabled={true}
        investigations={[
          makeInv({
            id: "i-1",
            events: [
              {
                id: "e1",
                author: "retrieval_agent",
                timestamp: 1,
                content: { parts: [{ text: "{}" }], role: "model" },
                actions: { stateDelta: { retrieval_output: "{}" } },
              },
            ],
          }),
        ]}
      />,
    );
    expect(screen.queryByTestId("agent-timeline")).not.toBeInTheDocument();
    const card = screen.getByTestId("investigation-card");
    await user.click(within(card).getByRole("button"));
    expect(screen.getByTestId("agent-timeline")).toBeInTheDocument();
  });
});
