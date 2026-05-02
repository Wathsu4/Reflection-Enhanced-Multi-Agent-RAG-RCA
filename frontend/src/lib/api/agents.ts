/**
 * Thin client for the Google ADK HTTP surface that fronts our agent
 * system (`rca-agent-system`). The conventions we depend on:
 *
 *   * App name is `rca_system` (matches the directory ADK auto-discovers
 *     in `agents_dir`).
 *   * Sessions are namespaced per (user, app); we use a single fixed
 *     `demo-user` for the prototype. Auth comes later.
 *   * `/run_sse` is a POST with a JSON body that streams Server-Sent
 *     Events. We can't use the browser `EventSource` API for it
 *     because that one only does GET.
 *
 * Mirrors the structure of `classifier.ts` for consistency: a typed
 * client with named error classes, plus a `__test__` export that pins
 * resolved configuration so tests don't fight env vars.
 */

import { v4 as uuidv4 } from "uuid";

import type { AdkEvent } from "@/lib/types";

const AGENT_URL =
  process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";
const APP_NAME = "rca_system";
const USER_ID = "demo-user";

export interface AgentHealthResponse {
  status: "ok" | "starting" | "error";
  /** e.g. "gemini-2.5-flash" -- comes from server.py /health. */
  model: string;
}

/** Network-level failures: DNS, connection refused, CORS, abort. */
export class AgentNetworkError extends Error {
  constructor(message: string, public cause?: unknown) {
    super(message);
    this.name = "AgentNetworkError";
  }
}

/** Non-2xx HTTP responses from the agent service. */
export class AgentHttpError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
  ) {
    super(message);
    this.name = "AgentHttpError";
  }
}

async function readDetail(res: Response): Promise<string | undefined> {
  try {
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) return undefined;
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d))
        .join("; ");
    }
    return undefined;
  } catch {
    return undefined;
  }
}

/** Wraps `fetch` so transport vs. server errors are distinguishable. */
async function safeFetch(
  url: string,
  init: RequestInit,
): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    throw new AgentNetworkError(
      `Could not reach agent service at ${url}`,
      err,
    );
  }
}

async function fetchJson<T>(
  url: string,
  init: RequestInit,
): Promise<T> {
  const res = await safeFetch(url, init);
  if (!res.ok) {
    const detail = await readDetail(res);
    const friendly =
      res.status >= 500
        ? `Agent service error (${res.status})`
        : `Agent rejected the request (${res.status})`;
    throw new AgentHttpError(res.status, friendly, detail);
  }
  try {
    return (await res.json()) as T;
  } catch (err) {
    throw new AgentHttpError(
      res.status,
      "Agent service returned invalid JSON",
      err instanceof Error ? err.message : undefined,
    );
  }
}

// -------------------- Public URL builders --------------------
// Exposed (with `__test__`) so unit tests can pin the path shape
// without spinning up a server.

function sessionUrl(sessionId: string): string {
  return `${AGENT_URL}/apps/${APP_NAME}/users/${USER_ID}/sessions/${sessionId}`;
}

function listSessionsUrl(): string {
  return `${AGENT_URL}/apps/${APP_NAME}/users/${USER_ID}/sessions`;
}

// -------------------- Public API --------------------

export async function getAgentHealth(
  signal?: AbortSignal,
): Promise<AgentHealthResponse> {
  return fetchJson<AgentHealthResponse>(`${AGENT_URL}/health`, {
    method: "GET",
    signal,
  });
}

export async function createSession(
  sessionId: string = uuidv4(),
): Promise<string> {
  await fetchJson<unknown>(sessionUrl(sessionId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  return sessionId;
}

export interface AdkSession {
  id: string;
  appName: string;
  userId: string;
  state: Record<string, unknown>;
  events: AdkEvent[];
  lastUpdateTime: number;
}

export async function getSession(sessionId: string): Promise<AdkSession> {
  return fetchJson<AdkSession>(sessionUrl(sessionId), { method: "GET" });
}

export async function listSessions(): Promise<AdkSession[]> {
  return fetchJson<AdkSession[]>(listSessionsUrl(), { method: "GET" });
}

/**
 * Parse a single `data:` SSE block into our `AdkEvent`. Exported so the
 * SSE generator below and the unit tests share one implementation.
 *
 * Returns `null` if the block isn't a parseable event (empty payload,
 * comment line, malformed JSON). The caller is expected to skip nulls.
 */
export function parseSseBlock(block: string): AdkEvent | null {
  // SSE allows multiple `data:` lines per block (concatenated with \n)
  // but ADK's emitter sends a single line per event. Be tolerant.
  const dataLines = block
    .split("\n")
    .filter((l) => l.startsWith("data:"))
    .map((l) => l.slice(5).trim());
  if (dataLines.length === 0) return null;
  const payload = dataLines.join("\n").trim();
  if (!payload) return null;
  try {
    return JSON.parse(payload) as AdkEvent;
  } catch {
    return null;
  }
}

/**
 * POST to `/run_sse` and yield parsed `AdkEvent`s as they arrive.
 *
 * Why a generator: callers can choose to consume eagerly (await for-of)
 * or lazily (iterate manually with cancellation), and the React hook
 * we layer on top can update state per-event without buffering the
 * whole run.
 *
 * Cancellation: pass an `AbortSignal` and call `.abort()` to tear down
 * the underlying connection; the generator returns cleanly.
 */
export async function* runAgentSSE(
  sessionId: string,
  userMessage: string,
  signal?: AbortSignal,
): AsyncGenerator<AdkEvent> {
  const res = await safeFetch(`${AGENT_URL}/run_sse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      app_name: APP_NAME,
      user_id: USER_ID,
      session_id: sessionId,
      new_message: { parts: [{ text: userMessage }], role: "user" },
      streaming: true,
    }),
  });

  if (!res.ok) {
    const detail = await readDetail(res);
    throw new AgentHttpError(
      res.status,
      `Agent run failed (${res.status})`,
      detail,
    );
  }
  if (!res.body) {
    throw new AgentHttpError(
      res.status,
      "Agent /run_sse returned no body",
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE blocks are delimited by a blank line (\n\n).
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const ev = parseSseBlock(block);
        if (ev) yield ev;
      }
    }
    // Drain any trailing block that wasn't terminated by \n\n.
    const tail = buffer.trim();
    if (tail) {
      const ev = parseSseBlock(tail);
      if (ev) yield ev;
    }
  } finally {
    // Some browsers leak the underlying connection if we don't release.
    try {
      reader.releaseLock();
    } catch {
      // releaseLock throws if already released; ignore.
    }
  }
}

// -------------------- test exports --------------------

export const __test__ = {
  AGENT_URL,
  APP_NAME,
  USER_ID,
  sessionUrl,
  listSessionsUrl,
};
