/**
 * Tests for the AgentStatusPill. Same approach as
 * `service-status-pill.test.tsx`: mock the underlying health hook
 * directly so the test exercises the presentation layer in isolation.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks/useAgentHealth", () => ({
  useAgentHealth: vi.fn(),
}));

import { AgentStatusPill } from "@/components/agent-status-pill";
import { useAgentHealth } from "@/lib/hooks/useAgentHealth";

const useHealth = useAgentHealth as unknown as ReturnType<typeof vi.fn>;

describe("<AgentStatusPill />", () => {
  it("renders the loading state with a pulsing dot", () => {
    useHealth.mockReturnValue({
      status: "loading",
      data: undefined,
      error: null,
      hasResolvedOnce: false,
    });
    render(<AgentStatusPill />);
    const pill = screen.getByTestId("agent-status-pill");
    expect(pill).toHaveAttribute("data-status", "loading");
    expect(screen.getByText(/checking/i)).toBeInTheDocument();
  });

  it("renders the healthy state with the model name", () => {
    useHealth.mockReturnValue({
      status: "ok",
      data: { status: "ok", model: "gemini-2.5-flash" },
      error: null,
      hasResolvedOnce: true,
    });
    render(<AgentStatusPill />);
    const pill = screen.getByTestId("agent-status-pill");
    expect(pill).toHaveAttribute("data-status", "ok");
    expect(screen.getByText(/agent/i)).toBeInTheDocument();
    // Pill should drop the `gemini-` prefix to keep the chip narrow.
    expect(screen.getByText(/2\.5-flash/i)).toBeInTheDocument();
    expect(pill.getAttribute("title")).toMatch(/online/i);
  });

  it("renders the offline state with a clear tooltip", () => {
    useHealth.mockReturnValue({
      status: "down",
      data: undefined,
      error: new Error("ECONNREFUSED"),
      hasResolvedOnce: true,
    });
    render(<AgentStatusPill />);
    const pill = screen.getByTestId("agent-status-pill");
    expect(pill).toHaveAttribute("data-status", "down");
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
    expect(pill.getAttribute("title")).toMatch(/unreachable/i);
  });

  it("does not show model info when offline", () => {
    useHealth.mockReturnValue({
      status: "down",
      data: undefined,
      error: new Error("down"),
      hasResolvedOnce: true,
    });
    render(<AgentStatusPill />);
    expect(screen.queryByText(/gemini|flash/i)).not.toBeInTheDocument();
  });
});
