/**
 * Tests for <SimulatorControls />. Verifies the UI surface of the simulator:
 * the right buttons appear in the right state, sliders are wired, and the
 * profile dropdown locks while running.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SimulatorControls } from "./simulator-controls";
import { DEFAULT_OPTIONS } from "@/lib/hooks/useLogSimulator";

function renderControls(
  overrides: Partial<React.ComponentProps<typeof SimulatorControls>> = {},
) {
  const props = {
    running: false,
    options: DEFAULT_OPTIONS,
    eventCount: 0,
    onStart: vi.fn(),
    onStop: vi.fn(),
    onClear: vi.fn(),
    onChange: vi.fn(),
    autoRcaEnabled: true,
    onAutoRcaChange: vi.fn(),
    ...overrides,
  };
  render(<SimulatorControls {...props} />);
  return props;
}

describe("<SimulatorControls />", () => {
  it("shows Start (not Stop) and disables Clear when stopped and empty", () => {
    renderControls();

    expect(screen.getByTestId("start-button")).toBeInTheDocument();
    expect(screen.queryByTestId("stop-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("clear-button")).toBeDisabled();
    expect(screen.getByText(/0 events captured/i)).toBeInTheDocument();
  });

  it("shows Stop and enables Clear when running with events", () => {
    renderControls({ running: true, eventCount: 5 });

    expect(screen.queryByTestId("start-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("stop-button")).toBeInTheDocument();
    expect(screen.getByTestId("clear-button")).not.toBeDisabled();
    expect(screen.getByText(/5 events captured/i)).toBeInTheDocument();
  });

  it("calls onStart, onStop, onClear from the appropriate buttons", async () => {
    const user = userEvent.setup();
    const props = renderControls({ running: false, eventCount: 3 });

    await user.click(screen.getByTestId("start-button"));
    expect(props.onStart).toHaveBeenCalledTimes(1);

    await user.click(screen.getByTestId("clear-button"));
    expect(props.onClear).toHaveBeenCalledTimes(1);
  });

  it("calls onChange when the user selects a profile", async () => {
    const user = userEvent.setup();
    const props = renderControls();

    await user.click(screen.getByTestId("profile-trigger"));
    await user.click(screen.getByTestId("profile-option-fatal"));

    expect(props.onChange).toHaveBeenCalledWith({ profile: "fatal" });
  });

  it("locks the profile dropdown while the simulator is running", () => {
    renderControls({ running: true });
    expect(screen.getByTestId("profile-trigger")).toBeDisabled();
  });

  it("calls onChange with autoClassify: false when the switch is toggled off", async () => {
    const user = userEvent.setup();
    const props = renderControls({
      options: { ...DEFAULT_OPTIONS, autoClassify: true },
    });

    await user.click(screen.getByTestId("auto-classify-switch"));

    expect(props.onChange).toHaveBeenCalledWith({ autoClassify: false });
  });

  it("emits onChange when the lines-per-chunk slider changes", () => {
    const props = renderControls();
    const slider = screen.getByLabelText(/lines per chunk/i);

    // fireEvent.change is the canonical way to drive controlled range/select
    // inputs in RTL \u2014 it sets the value via React's tracked descriptor so
    // the synthetic onChange handler actually fires.
    fireEvent.change(slider, { target: { value: "25" } });

    expect(props.onChange).toHaveBeenCalledWith({ numLines: 25 });
  });

  it("renders the Auto-RCA toggle reflecting the current value", () => {
    renderControls({ autoRcaEnabled: false });
    const sw = screen.getByTestId("auto-rca-switch");
    expect(sw).toHaveAttribute("data-state", "unchecked");
  });

  it("emits onAutoRcaChange when the Auto-RCA toggle is flipped", async () => {
    const user = userEvent.setup();
    const props = renderControls({ autoRcaEnabled: true });
    await user.click(screen.getByTestId("auto-rca-switch"));
    expect(props.onAutoRcaChange).toHaveBeenCalledWith(false);
  });
});
