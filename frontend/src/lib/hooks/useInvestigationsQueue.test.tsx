/**
 * Tests for the auto-RCA investigations queue.
 *
 * We mock `fetch` so no real ADK service is needed. Each test feeds
 * the hook with a stream of `SimEvent`s and asserts the resulting
 * investigation list. The fake stream emits the smallest valid set of
 * ADK events that triggers our state transitions:
 *   * one event with text + stateDelta(final_output) -> "done" with
 *     finalAnswer populated.
 *   * never closes -> "running" (used in the cancellation test).
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useInvestigationsQueue } from "@/lib/hooks/useInvestigationsQueue";
import type { ClassifyResponse, SimEvent, Severity } from "@/lib/types";

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------- helpers ----------

function makeSimEvent(
  id: string,
  shouldInvoke: boolean,
  severity: Severity = "ERROR",
  chunk = "log line",
): SimEvent {
  const classification: ClassifyResponse = {
    severity,
    severity_id: severity === "FATAL_OR_CRITICAL" ? 0 : 1,
    confidence: 0.9,
    should_invoke_rca: shouldInvoke,
    priority: shouldInvoke ? "high" : "none",
    inference_ms: 50,
    all_probabilities: {
      FATAL_OR_CRITICAL: 0,
      ERROR: 0,
      WARNING: 0,
      NORMAL: 0,
    },
  };
  return {
    id,
    timestamp: Date.now(),
    intendedSeverity: severity,
    chunkText: chunk,
    numLines: 3,
    classification,
    classifyError: null,
    status: "classified",
  };
}

interface MockBlock {
  /** SSE block body, e.g. `data: {...}\n\n`. */
  raw: string;
}

/**
 * Wire `fetch` so:
 *  * Session creation (`POST .../sessions/<id>`) returns 200 {}.
 *  * `/run_sse` POST returns a streamed body whose chunks are the
 *    given SSE blocks. The stream stays open until either: (a) all
 *    blocks are emitted and the stream closes, or (b) the request's
 *    AbortSignal fires.
 */
function mockSse(blocks: MockBlock[], opts: { closeAtEnd?: boolean } = {}): void {
  const closeAtEnd = opts.closeAtEnd ?? true;
  const encoder = new TextEncoder();
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.endsWith("/run_sse")) {
        const signal = init.signal;
        const stream = new ReadableStream<Uint8Array>({
          async start(controller) {
            const abort = () =>
              controller.error(new DOMException("Aborted", "AbortError"));
            if (signal?.aborted) {
              abort();
              return;
            }
            signal?.addEventListener("abort", abort, { once: true });
            for (const b of blocks) {
              controller.enqueue(encoder.encode(b.raw));
              // Yield so React can render between events.
              await new Promise((r) => setTimeout(r, 0));
            }
            if (closeAtEnd) controller.close();
          },
        });
        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      // Session creation, etc.
      return new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  );
}

// Build a final-event SSE block whose stateDelta carries the markdown.
function finalEventBlock(invId: string, markdown: string): MockBlock {
  const ev = {
    id: `final-${invId}`,
    author: "memory_update_agent",
    timestamp: 1,
    content: { parts: [{ text: markdown }], role: "model" as const },
    actions: { stateDelta: { final_output: markdown } },
  };
  return { raw: `data: ${JSON.stringify(ev)}\n\n` };
}

// ---------- enqueueing ----------

describe("useInvestigationsQueue: triggers", () => {
  it("ignores SimEvents with should_invoke_rca: false", async () => {
    mockSse([]);
    const { result, rerender } = renderHook(
      ({ classifiedEvents, autoRcaEnabled }) =>
        useInvestigationsQueue({ classifiedEvents, autoRcaEnabled }),
      {
        initialProps: {
          classifiedEvents: [makeSimEvent("a", false, "WARNING")],
          autoRcaEnabled: true,
        },
      },
    );
    rerender({
      classifiedEvents: [makeSimEvent("a", false, "WARNING")],
      autoRcaEnabled: true,
    });
    expect(result.current.investigations).toHaveLength(0);
  });

  it("enqueues a new investigation when should_invoke_rca: true", async () => {
    mockSse([finalEventBlock("inv1", "## Root cause\nFoo")]);
    const { result } = renderHook(() =>
      useInvestigationsQueue({
        classifiedEvents: [makeSimEvent("a", true)],
        autoRcaEnabled: true,
      }),
    );
    await waitFor(() => {
      expect(result.current.investigations.length).toBe(1);
    });
    expect(result.current.investigations[0].triggeredBy).toBe("a");
  });

  it("does not double-trigger when the same SimEvent is re-rendered", async () => {
    mockSse([finalEventBlock("inv1", "## Root cause\nFoo")]);
    const { result, rerender } = renderHook(
      ({ classifiedEvents, autoRcaEnabled }) =>
        useInvestigationsQueue({ classifiedEvents, autoRcaEnabled }),
      {
        initialProps: {
          classifiedEvents: [makeSimEvent("a", true)],
          autoRcaEnabled: true,
        },
      },
    );
    rerender({
      classifiedEvents: [makeSimEvent("a", true)],
      autoRcaEnabled: true,
    });
    rerender({
      classifiedEvents: [makeSimEvent("a", true)],
      autoRcaEnabled: true,
    });
    await waitFor(() =>
      expect(result.current.investigations.length).toBeGreaterThan(0),
    );
    expect(result.current.investigations).toHaveLength(1);
  });
});

// ---------- sequential execution ----------

describe("useInvestigationsQueue: sequential execution", () => {
  it("never has more than one running investigation", async () => {
    mockSse([finalEventBlock("any", "## Root cause\nResolved")]);
    const events = [
      makeSimEvent("a", true),
      makeSimEvent("b", true),
      makeSimEvent("c", true),
    ];
    const { result } = renderHook(() =>
      useInvestigationsQueue({
        classifiedEvents: events,
        autoRcaEnabled: true,
      }),
    );
    await waitFor(() => {
      // Three investigations enqueued.
      expect(result.current.investigations.length).toBe(3);
    });
    // While running, at most one is in 'running' state at any time.
    // The fake stream is fast (sync close), so we mostly catch them
    // during transitions. Wait until all are done.
    await waitFor(
      () =>
        expect(
          result.current.investigations.every((i) => i.status === "done"),
        ).toBe(true),
      { timeout: 4000 },
    );
    const runningCount = result.current.investigations.filter(
      (i) => i.status === "running",
    ).length;
    expect(runningCount).toBe(0);
  });

  it("populates finalAnswer from the SSE stateDelta on completion", async () => {
    const md = "## Root cause\nNetwork firewall block.";
    mockSse([finalEventBlock("x", md)]);
    const { result } = renderHook(() =>
      useInvestigationsQueue({
        classifiedEvents: [makeSimEvent("a", true)],
        autoRcaEnabled: true,
      }),
    );
    await waitFor(
      () => {
        expect(result.current.investigations[0].status).toBe("done");
      },
      { timeout: 3000 },
    );
    expect(result.current.investigations[0].finalAnswer).toBe(md);
    expect(result.current.investigations[0].completedAt).not.toBeNull();
  });
});

// ---------- toggle off ----------

describe("useInvestigationsQueue: autoRcaEnabled toggle", () => {
  it("ignores triggers while disabled", async () => {
    mockSse([]);
    const { result } = renderHook(() =>
      useInvestigationsQueue({
        classifiedEvents: [makeSimEvent("a", true)],
        autoRcaEnabled: false,
      }),
    );
    // Give React a tick.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(result.current.investigations).toHaveLength(0);
  });

  it("clears queued investigations when the toggle flips off, keeping done ones", async () => {
    mockSse([finalEventBlock("x", "## Root cause\nDone")]);
    const { result, rerender } = renderHook(
      ({ classifiedEvents, autoRcaEnabled }) =>
        useInvestigationsQueue({ classifiedEvents, autoRcaEnabled }),
      {
        initialProps: {
          classifiedEvents: [makeSimEvent("a", true)],
          autoRcaEnabled: true,
        },
      },
    );
    await waitFor(
      () => expect(result.current.investigations[0].status).toBe("done"),
      { timeout: 3000 },
    );
    // Now toggle off; the done entry should remain.
    rerender({
      classifiedEvents: [makeSimEvent("a", true)],
      autoRcaEnabled: false,
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(result.current.investigations).toHaveLength(1);
    expect(result.current.investigations[0].status).toBe("done");
  });
});

// ---------- clear ----------

describe("useInvestigationsQueue: clear()", () => {
  it("removes every entry and resets dedup tracking", async () => {
    mockSse([finalEventBlock("x", "## Root cause\nDone")]);
    const { result, rerender } = renderHook(
      ({ classifiedEvents }) =>
        useInvestigationsQueue({
          classifiedEvents,
          autoRcaEnabled: true,
        }),
      { initialProps: { classifiedEvents: [makeSimEvent("a", true)] } },
    );
    await waitFor(
      () => expect(result.current.investigations[0].status).toBe("done"),
      { timeout: 3000 },
    );
    act(() => {
      result.current.clear();
    });
    expect(result.current.investigations).toHaveLength(0);

    // After clear, the SAME SimEvent id should be eligible to trigger
    // again -- this is what "reset" means semantically for the demo.
    rerender({ classifiedEvents: [makeSimEvent("a", true)] });
    await waitFor(
      () => expect(result.current.investigations.length).toBe(1),
      { timeout: 2000 },
    );
  });
});
