import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ServiceHttpError,
  ServiceNetworkError,
  createHttpClient,
  readDetail,
} from "@/lib/api/http";

afterEach(() => {
  vi.restoreAllMocks();
});

class TestNetworkError extends ServiceNetworkError {
  name = "TestNetworkError";
}

class TestHttpError extends ServiceHttpError {
  name = "TestHttpError";
}

const client = createHttpClient({
  NetworkError: TestNetworkError,
  HttpError: TestHttpError,
  unreachableMessage: (url) => `unreachable: ${url}`,
  serverErrorMessage: (status) => `server error (${status})`,
  rejectedMessage: (status) => `rejected (${status})`,
  invalidJsonMessage: "invalid JSON",
});

function mockFetch(body: string, init?: ResponseInit): void {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(body, {
      status: 200,
      headers: { "Content-Type": "application/json" },
      ...init,
    }),
  );
}

describe("readDetail", () => {
  it("returns a string detail", async () => {
    const res = new Response(JSON.stringify({ detail: "boom" }), {
      headers: { "Content-Type": "application/json" },
    });
    await expect(readDetail(res)).resolves.toBe("boom");
  });

  it("joins FastAPI validation error arrays", async () => {
    const res = new Response(
      JSON.stringify({ detail: [{ msg: "too short" }, { msg: "required" }] }),
      { headers: { "Content-Type": "application/json" } },
    );
    await expect(readDetail(res)).resolves.toBe("too short; required");
  });

  it("ignores non-JSON bodies", async () => {
    const res = new Response("<html>500</html>", {
      headers: { "Content-Type": "text/html" },
    });
    await expect(readDetail(res)).resolves.toBeUndefined();
  });
});

describe("createHttpClient", () => {
  it("returns the parsed JSON body", async () => {
    mockFetch(JSON.stringify({ ok: true }));
    await expect(client.fetchJson("/x", {})).resolves.toEqual({ ok: true });
  });

  it("wraps fetch rejections in the configured network error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("ECONNREFUSED"));
    await expect(client.fetchJson("/x", {})).rejects.toBeInstanceOf(
      TestNetworkError,
    );
  });

  it("distinguishes 5xx from 4xx wording and lifts the detail", async () => {
    mockFetch(JSON.stringify({ detail: "nope" }), { status: 422 });
    await expect(client.fetchJson("/x", {})).rejects.toMatchObject({
      status: 422,
      message: "rejected (422)",
      detail: "nope",
    });

    mockFetch(JSON.stringify({ detail: "down" }), { status: 503 });
    await expect(client.fetchJson("/x", {})).rejects.toMatchObject({
      status: 503,
      message: "server error (503)",
    });
  });

  it("raises the configured HTTP error when a 2xx body isn't JSON", async () => {
    mockFetch("not json");
    const err = await client.fetchJson("/x", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(TestHttpError);
  });

  it("safeFetch returns the raw response for non-2xx", async () => {
    mockFetch("{}", { status: 500 });
    const res = await client.safeFetch("/x", {});
    expect(res.status).toBe(500);
  });
});
