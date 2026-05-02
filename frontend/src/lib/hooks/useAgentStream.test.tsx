import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { aggregateEvents, useAgentStream } from "@/lib/hooks/useAgentStream";
import type { AdkEvent } from "@/lib/types";

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------- pure aggregator ----------

describe("aggregateEvents", () => {
  it("groups events by author, preserving first-seen order", () => {
    const events: AdkEvent[] = [
      { id: "1", author: "a", timestamp: 1 },
      { id: "2", author: "b", timestamp: 2 },
      { id: "3", author: "a", timestamp: 3 },
    ];
    const groups = aggregateEvents(events);
    expect(groups.map((g) => g.author)).toEqual(["a", "b"]);
  });

  it("concatenates partial text fragments and replaces with final", () => {
    const events: AdkEvent[] = [
      {
        id: "1",
        author: "a",
        timestamp: 1,
        partial: true,
        content: { parts: [{ text: "Hello " }], role: "model" },
      },
      {
        id: "2",
        author: "a",
        timestamp: 2,
        partial: true,
        content: { parts: [{ text: "world" }], role: "model" },
      },
      {
        id: "3",
        author: "a",
        timestamp: 3,
        partial: false,
        content: { parts: [{ text: "Hello world" }], role: "model" }, // ADK final = aggregated
      },
    ];
    const [g] = aggregateEvents(events);
    expect(g.text).toBe("Hello world");
    expect(g.isComplete).toBe(true);
  });

  it("tracks tool call + response by callId across separate events", () => {
    const events: AdkEvent[] = [
      {
        id: "1",
        author: "r",
        timestamp: 1,
        content: {
          parts: [
            {
              functionCall: {
                id: "call-1",
                name: "retrieve_incidents",
                args: { query: "redis" },
              },
            },
          ],
          role: "model",
        },
      },
      {
        id: "2",
        author: "r",
        timestamp: 2,
        content: {
          parts: [
            {
              functionResponse: {
                id: "call-1",
                name: "retrieve_incidents",
                response: { hits: [{ incident_id: "redis-001" }] },
              },
            },
          ],
          role: "user",
        },
      },
    ];
    const [g] = aggregateEvents(events);
    expect(g.toolInvocations).toHaveLength(1);
    expect(g.toolInvocations[0].name).toBe("retrieve_incidents");
    expect(g.toolInvocations[0].args).toEqual({ query: "redis" });
    expect(g.toolInvocations[0].response).toEqual({
      hits: [{ incident_id: "redis-001" }],
    });
  });

  it("captures stateDelta writes and marks the agent complete", () => {
    const events: AdkEvent[] = [
      {
        id: "1",
        author: "memory_update_agent",
        timestamp: 1,
        actions: { stateDelta: { final_output: "## Root cause\nfoo" } },
      },
    ];
    const [g] = aggregateEvents(events);
    expect(g.stateWrites.final_output).toBe("## Root cause\nfoo");
    expect(g.isComplete).toBe(true);
  });

  it("does not double-count a tool call that arrives partial then final", () => {
    const events: AdkEvent[] = [
      {
        id: "1",
        author: "r",
        timestamp: 1,
        partial: true,
        content: {
          parts: [{ functionCall: { id: "c", name: "t", args: { q: "" } } }],
          role: "model",
        },
      },
      {
        id: "2",
        author: "r",
        timestamp: 2,
        partial: false,
        content: {
          parts: [{ functionCall: { id: "c", name: "t", args: { q: "redis" } } }],
          role: "model",
        },
      },
    ];
    const [g] = aggregateEvents(events);
    expect(g.toolInvocations).toHaveLength(1);
    expect(g.toolInvocations[0].args).toEqual({ q: "redis" });
  });
});

// ---------- live hook with mocked SSE ----------

function mockHttp(blocks: string[]): void {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const b of blocks) controller.enqueue(encoder.encode(b));
      controller.close();
    },
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (
    _input: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    if (init?.method === "POST" && String(_input).endsWith("/run_sse")) {
      return new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    }
    // createSession POST or any other JSON call.
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

describe("useAgentStream", () => {
  it("transitions idle -> streaming -> done and exposes finalMarkdown", async () => {
    const events: AdkEvent[] = [
      {
        id: "1",
        author: "retrieval_agent",
        timestamp: 1,
        content: { parts: [{ text: "{}" }], role: "model" },
        actions: { stateDelta: { retrieval_output: "{}" } },
      },
      {
        id: "2",
        author: "memory_update_agent",
        timestamp: 2,
        content: { parts: [{ text: "## Root cause\nfoo" }], role: "model" },
        actions: { stateDelta: { final_output: "## Root cause\nfoo" } },
      },
    ];
    mockHttp(events.map((e) => `data: ${JSON.stringify(e)}\n\n`));

    const { result } = renderHook(() => useAgentStream());
    expect(result.current.status).toBe("idle");
    await act(async () => {
      await result.current.run("hello");
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.events).toHaveLength(2);
    expect(result.current.groups.map((g) => g.author)).toEqual([
      "retrieval_agent",
      "memory_update_agent",
    ]);
    expect(result.current.finalMarkdown).toBe("## Root cause\nfoo");
  });

  it("populates state.error and status='error' when the SSE call 5xxs", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      if (init?.method === "POST" && String(input).endsWith("/run_sse")) {
        return new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    const { result } = renderHook(() => useAgentStream());
    await act(async () => {
      await result.current.run("hello");
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toMatch(/500/);
    expect(result.current.error).toMatch(/boom/);
  });

  it("treats user cancellation as a return-to-idle, not an error", async () => {
    // Mock fetch wires the user's AbortSignal into the stream's
    // controller so an abort mid-stream causes reader.read() to
    // reject -- mirroring real fetch behaviour. Without this, the
    // SSE reader would just hang because our test stream never
    // enqueues anything.
    vi.spyOn(globalThis, "fetch").mockImplementation(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      if (init?.method === "POST" && String(input).endsWith("/run_sse")) {
        const signal = init.signal;
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            const abort = () => controller.error(new DOMException("Aborted", "AbortError"));
            if (signal?.aborted) abort();
            else signal?.addEventListener("abort", abort, { once: true });
          },
        });
        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    const { result } = renderHook(() => useAgentStream());
    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run("x");
    });
    await waitFor(() => expect(result.current.status).toBe("streaming"));
    // Important: cancel + the resulting setState happen on the next
    // microtask, so we must let React's act flush them before
    // asserting. Wrapping the cancel + await in a single act() ensures
    // the post-abort `setState({status: "idle"})` is applied before
    // the assertion runs.
    await act(async () => {
      result.current.cancel();
      await runPromise!;
    });
    expect(result.current.status).toBe("idle");
    expect(result.current.error).toBeNull();
  });
});
