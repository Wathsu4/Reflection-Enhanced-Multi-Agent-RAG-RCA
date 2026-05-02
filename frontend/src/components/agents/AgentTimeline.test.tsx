/**
 * Tests for the `AgentTimeline` component.
 *
 * The component is purely presentational, so we feed it hand-crafted
 * `AgentRunGroup`s and assert what the user actually sees: number of
 * step cards, status badges, expandable tool details, and the final
 * markdown card.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AgentTimeline, stripJsonFences } from "@/components/agents/AgentTimeline";
import type { AgentRunGroup } from "@/lib/types";

function group(partial: Partial<AgentRunGroup> & { author: string }): AgentRunGroup {
  return {
    text: "",
    toolInvocations: [],
    isComplete: false,
    stateWrites: {},
    firstTs: 0,
    lastTs: 0,
    ...partial,
  };
}

// ---------- empty-state ----------

describe("AgentTimeline empty state", () => {
  it("shows a hint when status is idle and groups is empty", () => {
    render(<AgentTimeline status="idle" groups={[]} finalMarkdown={null} />);
    expect(screen.getByText(/run an analysis/i)).toBeInTheDocument();
  });

  it("shows a 'waiting' placeholder while streaming with no events yet", () => {
    render(
      <AgentTimeline status="streaming" groups={[]} finalMarkdown={null} />,
    );
    expect(screen.getByText(/waiting for the first agent/i)).toBeInTheDocument();
  });
});

// ---------- per-agent rendering ----------

describe("AgentTimeline step rendering", () => {
  it("renders one card per group, in order", () => {
    render(
      <AgentTimeline
        status="done"
        groups={[
          group({ author: "retrieval_agent", isComplete: true }),
          group({ author: "reasoning_agent", isComplete: true }),
        ]}
        finalMarkdown={null}
      />,
    );
    const steps = screen.getAllByTestId("agent-step");
    expect(steps).toHaveLength(2);
    // The order in the DOM matches the input order.
    expect(steps[0]).toHaveAttribute("data-author", "retrieval_agent");
    expect(steps[1]).toHaveAttribute("data-author", "reasoning_agent");
  });

  it("shows friendly labels for known sub-agents", () => {
    render(
      <AgentTimeline
        status="done"
        groups={[
          group({ author: "retrieval_agent", isComplete: true }),
          group({ author: "memory_update_agent", isComplete: true }),
        ]}
        finalMarkdown={null}
      />,
    );
    expect(screen.getByText("Retrieval")).toBeInTheDocument();
    expect(screen.getByText("Memory update")).toBeInTheDocument();
  });

  it("falls back to the raw author name for unknown agents", () => {
    render(
      <AgentTimeline
        status="done"
        groups={[group({ author: "future_agent_v2" })]}
        finalMarkdown={null}
      />,
    );
    // The label cell shows the raw name when no AGENT_META entry exists.
    expect(screen.getAllByText("future_agent_v2").length).toBeGreaterThan(0);
  });

  it("marks the LAST streaming group as 'working' and others as 'done'", () => {
    render(
      <AgentTimeline
        status="streaming"
        groups={[
          group({ author: "retrieval_agent", isComplete: true }),
          group({ author: "reasoning_agent", isComplete: false }),
        ]}
        finalMarkdown={null}
      />,
    );
    const steps = screen.getAllByTestId("agent-step");
    // First step: complete -> "done" badge.
    expect(within(steps[0]).getByText("done")).toBeInTheDocument();
    // Last step (reasoning_agent), not complete, while streaming -> "working".
    expect(within(steps[1]).getByText("working")).toBeInTheDocument();
  });

  it("does not show 'working' for any step when status is 'done'", () => {
    render(
      <AgentTimeline
        status="done"
        groups={[
          group({ author: "retrieval_agent", isComplete: true }),
          group({ author: "reasoning_agent", isComplete: true }),
        ]}
        finalMarkdown={null}
      />,
    );
    expect(screen.queryByText("working")).not.toBeInTheDocument();
  });
});

// ---------- tool call cards ----------

describe("AgentTimeline tool call rendering", () => {
  it("renders one tool card per invocation", () => {
    render(
      <AgentTimeline
        status="done"
        groups={[
          group({
            author: "retrieval_agent",
            isComplete: true,
            toolInvocations: [
              {
                callId: "c1",
                name: "retrieve_incidents",
                args: { query: "redis" },
                response: { hits: [] },
              },
              {
                callId: "c2",
                name: "another_tool",
                args: {},
              },
            ],
          }),
        ]}
        finalMarkdown={null}
      />,
    );
    const cards = screen.getAllByTestId("tool-call-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("data-tool-name", "retrieve_incidents");
  });

  it("expands to show args + response when clicked", async () => {
    const user = userEvent.setup();
    render(
      <AgentTimeline
        status="done"
        groups={[
          group({
            author: "retrieval_agent",
            isComplete: true,
            toolInvocations: [
              {
                callId: "c1",
                name: "retrieve_incidents",
                args: { query: "redis-conn-refused" },
                response: { hits: [{ incident_id: "redis-conn-refused-001" }] },
              },
            ],
          }),
        ]}
        finalMarkdown={null}
      />,
    );

    // Collapsed by default: args/response not visible.
    expect(screen.queryByText(/redis-conn-refused-001/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /retrieve_incidents/ }));

    // Now the args + response panes are mounted.
    expect(screen.getByText(/"redis-conn-refused"/)).toBeInTheDocument();
    expect(screen.getByText(/redis-conn-refused-001/)).toBeInTheDocument();
  });

  it("flags pending tool calls (no response yet) in the header", () => {
    render(
      <AgentTimeline
        status="streaming"
        groups={[
          group({
            author: "reflection_agent",
            isComplete: false,
            toolInvocations: [
              {
                callId: "c1",
                name: "record_reflection",
                args: { overall_quality: "high" },
              },
            ],
          }),
        ]}
        finalMarkdown={null}
      />,
    );
    expect(screen.getByText(/pending/)).toBeInTheDocument();
  });
});

// ---------- final markdown card ----------

describe("AgentTimeline final markdown card", () => {
  it("renders the final markdown when provided", () => {
    render(
      <AgentTimeline
        status="done"
        groups={[group({ author: "memory_update_agent", isComplete: true })]}
        finalMarkdown={"## Root cause\nRedis firewall block"}
      />,
    );
    expect(screen.getByTestId("final-rca-card")).toBeInTheDocument();
    expect(screen.getByTestId("markdown-view")).toBeInTheDocument();
    // The <h2> from `## Root cause` should be present.
    expect(
      screen.getByRole("heading", { level: 2, name: /Root cause/ }),
    ).toBeInTheDocument();
  });

  it("does NOT render the final card when finalMarkdown is null", () => {
    render(
      <AgentTimeline
        status="streaming"
        groups={[group({ author: "retrieval_agent" })]}
        finalMarkdown={null}
      />,
    );
    expect(screen.queryByTestId("final-rca-card")).not.toBeInTheDocument();
  });
});

// ---------- helper exposed for direct testing ----------

describe("stripJsonFences", () => {
  it("returns the input unchanged when no fences are present", () => {
    expect(stripJsonFences('{"foo": 1}')).toBe('{"foo": 1}');
  });

  it("strips ```json ... ``` fences", () => {
    expect(stripJsonFences('```json\n{"foo": 1}\n```')).toBe('{"foo": 1}');
  });

  it("strips bare ``` ... ``` fences", () => {
    expect(stripJsonFences('```\n{"foo": 1}\n```')).toBe('{"foo": 1}');
  });

  it("does not strip a fence that is unbalanced", () => {
    expect(stripJsonFences('```json\n{"foo": 1}')).toBe('```json\n{"foo": 1}');
  });
});
