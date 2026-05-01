/**
 * Tests for the ServiceStatusPill. The pill is a thin presentational layer
 * over `useClassifierHealth`, so we mock the hook directly rather than
 * mocking fetch \u2014 the hook itself is exercised in
 * `useClassifierHealth.test.tsx`.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/hooks/useClassifierHealth", () => ({
  useClassifierHealth: vi.fn(),
}));

import { useClassifierHealth } from "@/lib/hooks/useClassifierHealth";
import { ServiceStatusPill } from "./service-status-pill";

const useHealth = useClassifierHealth as unknown as ReturnType<typeof vi.fn>;

describe("<ServiceStatusPill />", () => {
  it("renders the loading state with a pulsing dot", () => {
    useHealth.mockReturnValue({
      status: "loading",
      data: undefined,
      error: null,
      hasResolvedOnce: false,
    });

    render(<ServiceStatusPill />);

    const pill = screen.getByTestId("service-status-pill");
    expect(pill).toHaveAttribute("data-status", "loading");
    expect(screen.getByText(/checking/i)).toBeInTheDocument();
  });

  it("renders the healthy state with the device name", () => {
    useHealth.mockReturnValue({
      status: "ok",
      data: { status: "ok", model_loaded: true, device: "mps" },
      error: null,
      hasResolvedOnce: true,
    });

    render(<ServiceStatusPill />);

    const pill = screen.getByTestId("service-status-pill");
    expect(pill).toHaveAttribute("data-status", "ok");
    expect(screen.getByText(/classifier/i)).toBeInTheDocument();
    expect(screen.getByText(/mps/i)).toBeInTheDocument();
    expect(pill.getAttribute("title")).toMatch(/online/i);
  });

  it("renders the offline state with a clear tooltip", () => {
    useHealth.mockReturnValue({
      status: "down",
      data: undefined,
      error: new Error("ECONNREFUSED"),
      hasResolvedOnce: true,
    });

    render(<ServiceStatusPill />);

    const pill = screen.getByTestId("service-status-pill");
    expect(pill).toHaveAttribute("data-status", "down");
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
    expect(pill.getAttribute("title")).toMatch(/unreachable/i);
  });

  it("does not show device info when offline", () => {
    useHealth.mockReturnValue({
      status: "down",
      data: undefined,
      error: new Error("down"),
      hasResolvedOnce: true,
    });

    render(<ServiceStatusPill />);

    expect(screen.queryByText(/mps|cpu|cuda/i)).not.toBeInTheDocument();
  });
});
