import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAgentHealth } from "@/lib/hooks/useAgentHealth";

afterEach(() => {
  vi.restoreAllMocks();
});

function wrapper(): (p: { children: ReactNode }) => JSX.Element {
  // Fresh QueryClient per test so tests don't leak cache between each other.
  // `retry: false` matters less now that we override the polling interval to
  // a huge number, but it still kills react-query's default backoff so the
  // hook's own `retry: 1` is the only retry that runs.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

// Disable polling during tests so we don't keep firing fetches mid-assertion;
// 100_000 ms is effectively "never re-poll within the test lifetime".
const TEST_OPTS = { intervalMs: 100_000 } as const;
// `retry: 1` in the production hook means a failed fetch retries once with
// react-query's default ~1s backoff. Tests therefore need >1s of slack.
const LONG = { timeout: 3000 } as const;

describe("useAgentHealth", () => {
  it("starts in 'loading' and transitions to 'ok' on a healthy response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "ok", model: "gemini-2.5-flash" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const { result } = renderHook(() => useAgentHealth(TEST_OPTS), {
      wrapper: wrapper(),
    });
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ok"));
    expect(result.current.data?.model).toBe("gemini-2.5-flash");
  });

  it("transitions to 'down' when fetch rejects (service unreachable)", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fail"));
    const { result } = renderHook(() => useAgentHealth(TEST_OPTS), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.status).toBe("down"), LONG);
  });

  it("transitions to 'down' when /health returns 503", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "warming up" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { result } = renderHook(() => useAgentHealth(TEST_OPTS), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.status).toBe("down"), LONG);
  });
});
