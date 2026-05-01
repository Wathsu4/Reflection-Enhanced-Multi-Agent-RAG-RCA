/**
 * Tests for the useLogSimulator hook.
 *
 * Mocks the API client directly (rather than `fetch`) because the hook only
 * cares about the resolved/rejected promise from the client.
 *
 * Uses **real timers with very short intervals** (e.g. 20ms). RTL's
 * `waitFor` polls with `setInterval`; under Vitest's fake timers that
 * polling stops, which makes hook tests that wait on async state updates
 * deadlock. Real timers + tiny intervals keep tests deterministic enough
 * (each tick takes a millisecond or two) and let `waitFor` work normally.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import {
  useLogSimulator,
  DEFAULT_OPTIONS,
} from "./useLogSimulator";

// Hoist the mocks so they're wired before the hook imports the API client.
const generateLogsMock = vi.hoisted(() => vi.fn());
const classifyMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/classifier", () => ({
  generateLogs: generateLogsMock,
  classify: classifyMock,
}));

const baseGenResponse = {
  log_chunk: "ERROR Connection refused",
  intended_severity: "ERROR" as const,
  num_lines: 5,
};

const baseClassifyResponse = {
  severity: "ERROR" as const,
  severity_id: 1 as const,
  confidence: 0.91,
  should_invoke_rca: true,
  priority: "high" as const,
  inference_ms: 33,
  all_probabilities: {
    FATAL_OR_CRITICAL: 0.04,
    ERROR: 0.91,
    WARNING: 0.04,
    NORMAL: 0.01,
  },
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("useLogSimulator", () => {
  beforeEach(() => {
    generateLogsMock.mockReset();
    classifyMock.mockReset();
    generateLogsMock.mockResolvedValue(baseGenResponse);
    classifyMock.mockResolvedValue(baseClassifyResponse);
  });

  it("starts in a stopped, empty state with the default options", () => {
    const { result } = renderHook(() => useLogSimulator());

    expect(result.current.running).toBe(false);
    expect(result.current.events).toEqual([]);
    expect(result.current.latest).toBeNull();
    expect(result.current.options).toEqual(DEFAULT_OPTIONS);
  });

  it("appends a generated event and then a classified event on the first tick", async () => {
    const { result, unmount } = renderHook(() => useLogSimulator());

    act(() => result.current.start({ intervalMs: 5_000 }));

    await waitFor(() => {
      expect(result.current.events.length).toBe(1);
      expect(result.current.events[0]!.status).toBe("classified");
    });

    expect(result.current.events[0]!.classification).toEqual(
      baseClassifyResponse,
    );
    expect(result.current.events[0]!.intendedSeverity).toBe("ERROR");
    expect(result.current.events[0]!.classifyError).toBeNull();
    expect(result.current.running).toBe(true);

    unmount();
  });

  it("schedules subsequent ticks at the configured interval", async () => {
    const { result, unmount } = renderHook(() => useLogSimulator());

    act(() => result.current.start({ intervalMs: 20 }));

    await waitFor(() => expect(result.current.events.length).toBeGreaterThanOrEqual(2));
    expect(generateLogsMock).toHaveBeenCalledTimes(
      result.current.events.length,
    );
    // Newest event is at index 0.
    expect(result.current.latest).toBe(result.current.events[0]);

    act(() => result.current.stop());
    unmount();
  });

  it("skips classify() when autoClassify is false", async () => {
    const { result, unmount } = renderHook(() => useLogSimulator());

    act(() =>
      result.current.start({ autoClassify: false, intervalMs: 5_000 }),
    );

    await waitFor(() => expect(result.current.events.length).toBe(1));

    expect(classifyMock).not.toHaveBeenCalled();
    expect(result.current.events[0]!.status).toBe("pending");
    expect(result.current.events[0]!.classification).toBeNull();

    act(() => result.current.stop());
    unmount();
  });

  it("marks an event as 'error' when classify() rejects, but keeps looping", async () => {
    classifyMock.mockRejectedValueOnce(new Error("classifier down"));

    const { result, unmount } = renderHook(() => useLogSimulator());
    act(() => result.current.start({ intervalMs: 20 }));

    // Wait until at least one event has been marked as 'error'. Note that
    // events are stored newest-first, so multiple ticks may have already
    // completed by the time `waitFor` checks; we just need *some* errored
    // event in the buffer.
    await waitFor(() => {
      expect(
        result.current.events.some((e) => e.status === "error"),
      ).toBe(true);
    });

    const erroredEvent = result.current.events.find(
      (e) => e.status === "error",
    );
    expect(erroredEvent?.classifyError).toContain("classifier down");
    expect(result.current.lastError?.message).toBe("classifier down");

    // Subsequent ticks (with classify now succeeding) should produce
    // classified events too.
    await waitFor(() =>
      expect(
        result.current.events.some((e) => e.status === "classified"),
      ).toBe(true),
    );

    act(() => result.current.stop());
    unmount();
  });

  it("records lastError but does not append an event when generateLogs() rejects", async () => {
    generateLogsMock.mockRejectedValueOnce(new Error("network"));

    const { result, unmount } = renderHook(() => useLogSimulator());
    act(() => result.current.start({ intervalMs: 5_000 }));

    await waitFor(() =>
      expect(result.current.lastError?.message).toBe("network"),
    );
    expect(result.current.events).toEqual([]);

    act(() => result.current.stop());
    unmount();
  });

  it("stop() halts further ticks", async () => {
    const { result, unmount } = renderHook(() => useLogSimulator());

    act(() => result.current.start({ intervalMs: 20 }));
    await waitFor(() => expect(result.current.events.length).toBeGreaterThanOrEqual(1));

    act(() => result.current.stop());
    const countAtStop = result.current.events.length;
    expect(result.current.running).toBe(false);

    // Wait long enough that we'd see several more ticks if the loop were
    // still alive, then assert nothing changed.
    await sleep(120);
    expect(result.current.events.length).toBe(countAtStop);

    unmount();
  });

  it("clear() empties the buffer and discards any in-flight tick result", async () => {
    // Make classify() slow so we can clear() before it resolves.
    let releaseClassify: (v: typeof baseClassifyResponse) => void = () => {};
    classifyMock.mockReturnValueOnce(
      new Promise((resolve) => {
        releaseClassify = resolve;
      }),
    );

    const { result, unmount } = renderHook(() => useLogSimulator());
    act(() => result.current.start({ intervalMs: 5_000 }));

    // Wait for the pending event to land.
    await waitFor(() => expect(result.current.events.length).toBe(1));
    expect(result.current.events[0]!.status).toBe("pending");

    // Clear the buffer \u2014 classify is still in flight.
    act(() => result.current.clear());
    expect(result.current.events).toEqual([]);

    // Now release the in-flight classify; it must NOT repopulate the
    // buffer because clear() invalidated the generation counter.
    act(() => releaseClassify(baseClassifyResponse));
    await sleep(20);
    expect(result.current.events).toEqual([]);

    act(() => result.current.stop());
    unmount();
  });

  it("respects maxEvents as a ring buffer cap", async () => {
    const { result, unmount } = renderHook(() => useLogSimulator());

    act(() =>
      result.current.start({
        intervalMs: 10,
        maxEvents: 3,
        autoClassify: false,
      }),
    );

    // Let several ticks run, then assert the buffer is bounded.
    await waitFor(() =>
      expect(generateLogsMock.mock.calls.length).toBeGreaterThanOrEqual(5),
    );
    expect(result.current.events.length).toBeLessThanOrEqual(3);

    act(() => result.current.stop());
    unmount();
  });

  it("updateOptions() takes effect on the next tick", async () => {
    const { result, unmount } = renderHook(() => useLogSimulator());

    act(() => result.current.start({ profile: "mixed", intervalMs: 20 }));
    await waitFor(() => expect(generateLogsMock).toHaveBeenCalled());
    const callsAtSwitch = generateLogsMock.mock.calls.length;
    expect(generateLogsMock.mock.calls[0]![0]).toMatchObject({
      profile: "mixed",
    });

    act(() => result.current.updateOptions({ profile: "fatal" }));

    await waitFor(() =>
      expect(generateLogsMock.mock.calls.length).toBeGreaterThan(callsAtSwitch),
    );
    // Find the first call made after the update.
    const laterCall = generateLogsMock.mock.calls
      .slice(callsAtSwitch)
      .find((c) => (c[0] as { profile?: string }).profile === "fatal");
    expect(laterCall).toBeDefined();

    act(() => result.current.stop());
    unmount();
  });
});
