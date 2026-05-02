import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AgentHttpError,
  AgentNetworkError,
  __test__,
  createSession,
  getAgentHealth,
  parseSseBlock,
  runAgentSSE,
} from "@/lib/api/agents";
import type { AdkEvent } from "@/lib/types";

// ---------- helpers ----------

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetchOk<T>(body: T, init?: ResponseInit): void {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
      ...init,
    }),
  );
}

function mockFetchStatus(status: number, body: unknown): void {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockFetchSseStream(blocks: string[]): void {
  // Build a ReadableStream that emits each block (already \n\n-terminated)
  // as a separate chunk so the SSE parser sees a realistic split.
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const b of blocks) controller.enqueue(encoder.encode(b));
      controller.close();
    },
  });
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }),
  );
}

// ---------- URL builders ----------

describe("agents URL builders", () => {
  it("builds session URL with app + user namespaced", () => {
    const url = __test__.sessionUrl("abc-123");
    expect(url).toMatch(/\/apps\/rca_system\/users\/demo-user\/sessions\/abc-123$/);
  });

  it("builds list-sessions URL without an id", () => {
    const url = __test__.listSessionsUrl();
    expect(url).toMatch(/\/apps\/rca_system\/users\/demo-user\/sessions$/);
    expect(url).not.toMatch(/\/sessions\/[^/]+$/);
  });
});

// ---------- parseSseBlock ----------

describe("parseSseBlock", () => {
  it("parses a single-line data: payload", () => {
    const ev = parseSseBlock(`data: {"id":"e1","author":"x","timestamp":1}`);
    expect(ev?.id).toBe("e1");
    expect(ev?.author).toBe("x");
  });

  it("returns null on a non-JSON data: payload", () => {
    expect(parseSseBlock("data: not-json")).toBeNull();
  });

  it("returns null on a block with no data: line", () => {
    expect(parseSseBlock(":heartbeat\nevent: ping")).toBeNull();
  });

  it("preserves nested camelCase fields like functionCall", () => {
    const ev = parseSseBlock(
      `data: {"id":"e2","author":"r","timestamp":1,"content":{"parts":[{"functionCall":{"name":"foo","args":{"q":"x"}}}],"role":"model"}}`,
    );
    expect(ev?.content?.parts[0].functionCall?.name).toBe("foo");
  });
});

// ---------- getAgentHealth ----------

describe("getAgentHealth", () => {
  it("returns the parsed health payload on 200", async () => {
    mockFetchOk({ status: "ok", model: "gemini-2.5-flash" });
    const h = await getAgentHealth();
    expect(h.status).toBe("ok");
    expect(h.model).toBe("gemini-2.5-flash");
  });

  it("throws AgentNetworkError when fetch itself rejects", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fail"));
    await expect(getAgentHealth()).rejects.toBeInstanceOf(AgentNetworkError);
  });

  it("throws AgentHttpError on a non-2xx response, surfacing detail", async () => {
    mockFetchStatus(503, { detail: "model not loaded" });
    await expect(getAgentHealth()).rejects.toMatchObject({
      name: "AgentHttpError",
      status: 503,
      detail: "model not loaded",
    });
  });
});

// ---------- createSession ----------

describe("createSession", () => {
  it("POSTs the session id and returns it", async () => {
    const fetchSpy = mockFetchOk({});
    const id = await createSession("session-xyz");
    expect(id).toBe("session-xyz");
    const [url, init] = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/sessions/session-xyz");
    expect(init).toMatchObject({ method: "POST" });
    fetchSpy; // silence unused
  });

  it("auto-generates a UUID when none passed", async () => {
    mockFetchOk({});
    const id = await createSession();
    expect(id).toMatch(/^[0-9a-f-]{36}$/i);
  });
});

// ---------- runAgentSSE ----------

describe("runAgentSSE", () => {
  it("parses and yields events from the byte stream", async () => {
    const evs: AdkEvent[] = [
      { id: "e1", author: "retrieval_agent", timestamp: 1, partial: true },
      { id: "e2", author: "retrieval_agent", timestamp: 2 },
    ];
    mockFetchSseStream([
      `data: ${JSON.stringify(evs[0])}\n\n`,
      `data: ${JSON.stringify(evs[1])}\n\n`,
    ]);
    const seen: AdkEvent[] = [];
    for await (const ev of runAgentSSE("s1", "hello")) seen.push(ev);
    expect(seen).toHaveLength(2);
    expect(seen[0].id).toBe("e1");
    expect(seen[1].id).toBe("e2");
  });

  it("handles a chunk that splits one event across two reads", async () => {
    // Realistic edge case: TCP delivers the JSON in two halves.
    const ev = { id: "split", author: "a", timestamp: 1, content: { parts: [{ text: "hi" }], role: "model" as const } };
    const full = `data: ${JSON.stringify(ev)}\n\n`;
    const half = full.length / 2;
    mockFetchSseStream([full.slice(0, half), full.slice(half)]);

    const seen: AdkEvent[] = [];
    for await (const e of runAgentSSE("s2", "x")) seen.push(e);
    expect(seen).toEqual([ev]);
  });

  it("drops blocks without a parseable JSON payload but keeps later ones", async () => {
    mockFetchSseStream([
      `:heartbeat\n\n`, // SSE comment, no data:
      `data: garbage{not json\n\n`,
      `data: ${JSON.stringify({ id: "ok", author: "a", timestamp: 1 })}\n\n`,
    ]);

    const seen: AdkEvent[] = [];
    for await (const e of runAgentSSE("s3", "x")) seen.push(e);
    expect(seen).toEqual([{ id: "ok", author: "a", timestamp: 1 }]);
  });

  it("throws AgentHttpError on a non-2xx response and never yields", async () => {
    mockFetchStatus(500, { detail: "boom" });
    const gen = runAgentSSE("s4", "x");
    await expect(gen.next()).rejects.toMatchObject({
      name: "AgentHttpError",
      status: 500,
      detail: "boom",
    });
  });
});
