/**
 * Tests for the useClassifierHealth hook. The hook composes a TanStack Query
 * `useQuery` with a derived status. We exercise it by mocking the underlying
 * fetch and asserting the derived status across the loading / ok / down
 * states. We deliberately do NOT test the polling interval here \u2014 that's a
 * react-query implementation detail.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useClassifierHealth } from "./useClassifierHealth";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

function makeWrapper() {
  // Disable retries and caching between tests so each test starts fresh.
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

describe("useClassifierHealth", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("starts in 'loading' before the first poll resolves", () => {
    fetchSpy.mockImplementation(() => new Promise(() => {})); // never resolves
    const { result } = renderHook(
      () => useClassifierHealth({ intervalMs: 100_000 }),
      { wrapper: makeWrapper() },
    );

    expect(result.current.status).toBe("loading");
    expect(result.current.data).toBeUndefined();
  });

  it("transitions to 'ok' when /health returns status:ok with model_loaded:true", async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ status: "ok", model_loaded: true, device: "mps" }),
    );
    const { result } = renderHook(
      () => useClassifierHealth({ intervalMs: 100_000 }),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.status).toBe("ok"));
    expect(result.current.data?.device).toBe("mps");
  });

  it("transitions to 'down' when /health reports model_loaded:false", async () => {
    // status:"ok" but the model failed to load \u2014 still considered down.
    fetchSpy.mockResolvedValue(
      jsonResponse({ status: "ok", model_loaded: false, device: "cpu" }),
    );
    const { result } = renderHook(
      () => useClassifierHealth({ intervalMs: 100_000 }),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.status).toBe("down"));
  });

  it("transitions to 'down' when fetch rejects (service unreachable)", async () => {
    fetchSpy.mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(
      () => useClassifierHealth({ intervalMs: 100_000 }),
      { wrapper: makeWrapper() },
    );

    // The hook retries once on failure (production behavior). Default retry
    // delay is ~1s, so we need a >1s window for the second attempt + render.
    await waitFor(() => expect(result.current.status).toBe("down"), {
      timeout: 3000,
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it("transitions to 'down' when /health returns 503", async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ detail: "starting up" }, { status: 503 }),
    );
    const { result } = renderHook(
      () => useClassifierHealth({ intervalMs: 100_000 }),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.status).toBe("down"), {
      timeout: 3000,
    });
  });
});
