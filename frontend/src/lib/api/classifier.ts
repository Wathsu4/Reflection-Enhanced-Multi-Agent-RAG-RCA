import type { ClassifyResponse } from "@/lib/types";

/**
 * Resolves the base URL of the classifier service.
 *
 * Phase 1 ran without a backend, so the absence of NEXT_PUBLIC_CLASSIFIER_URL
 * implicitly enabled a mock. Phase 3 flips this: the real service is the
 * default, and the mock is opt-in via NEXT_PUBLIC_USE_MOCK="true" so devs can
 * still work offline.
 */
const CLASSIFIER_URL = process.env.NEXT_PUBLIC_CLASSIFIER_URL ?? "http://localhost:8001";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

export interface HealthResponse {
  status: "ok" | "starting" | "error";
  model_loaded: boolean;
  device: string;
}

/** Fired when fetch itself rejects (DNS, connection refused, CORS, abort). */
export class ClassifierNetworkError extends Error {
  constructor(message: string, public cause?: unknown) {
    super(message);
    this.name = "ClassifierNetworkError";
  }
}

/** Fired when the server returns a non-2xx response. */
export class ClassifierHttpError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Parsed error payload from the server (FastAPI's `detail`), if any. */
    public detail?: string,
  ) {
    super(message);
    this.name = "ClassifierHttpError";
  }
}

/** Try to extract FastAPI-style `{detail: "..."}` from a failed response. */
async function readDetail(res: Response): Promise<string | undefined> {
  try {
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) return undefined;
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      // FastAPI 422 returns an array of validation errors; join them.
      return body.detail
        .map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d))
        .join("; ");
    }
    return undefined;
  } catch {
    return undefined;
  }
}

async function jsonFetch<T>(
  url: string,
  init: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    // `fetch` only rejects on network failure / abort.
    throw new ClassifierNetworkError(
      `Could not reach classifier service at ${url}`,
      err,
    );
  }

  if (!res.ok) {
    const detail = await readDetail(res);
    const friendly =
      res.status >= 500
        ? `Classifier service error (${res.status})`
        : `Classifier rejected the request (${res.status})`;
    throw new ClassifierHttpError(res.status, friendly, detail);
  }

  try {
    return (await res.json()) as T;
  } catch (err) {
    throw new ClassifierHttpError(
      res.status,
      "Classifier returned invalid JSON",
      err instanceof Error ? err.message : undefined,
    );
  }
}

export async function classify(logChunk: string): Promise<ClassifyResponse> {
  if (USE_MOCK) return mockClassify(logChunk);
  return jsonFetch<ClassifyResponse>(`${CLASSIFIER_URL}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ log_chunk: logChunk }),
  });
}

export async function getClassifierHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  if (USE_MOCK) {
    return { status: "ok", model_loaded: true, device: "mock" };
  }
  return jsonFetch<HealthResponse>(`${CLASSIFIER_URL}/health`, {
    method: "GET",
    signal,
  });
}

// Exposed so tests can pin behavior even when devs override env vars locally.
export const __test__ = {
  CLASSIFIER_URL,
  USE_MOCK,
};

// ---------- mock fallback ----------
// Naive keyword-based mock. Good enough to exercise the UI offline.
function mockClassify(chunk: string): Promise<ClassifyResponse> {
  const lower = chunk.toLowerCase();
  let severity: ClassifyResponse["severity"] = "NORMAL";
  if (/fatal|panic|core dump|out of memory/.test(lower))
    severity = "FATAL_OR_CRITICAL";
  else if (/error|exception|failed|refused|5\d\d/.test(lower))
    severity = "ERROR";
  else if (/warn|deprecat|retry|slow|latency/.test(lower)) severity = "WARNING";

  const conf = 0.8 + Math.random() * 0.15;
  const probs = { FATAL_OR_CRITICAL: 0, ERROR: 0, WARNING: 0, NORMAL: 0 };
  probs[severity] = conf;
  const remainder = (1 - conf) / 3;
  for (const k of Object.keys(probs) as (keyof typeof probs)[]) {
    if (k !== severity) probs[k] = remainder;
  }

  return new Promise((r) =>
    setTimeout(
      () =>
        r({
          severity,
          severity_id: [
            "FATAL_OR_CRITICAL",
            "ERROR",
            "WARNING",
            "NORMAL",
          ].indexOf(severity) as 0 | 1 | 2 | 3,
          confidence: conf,
          should_invoke_rca:
            severity === "FATAL_OR_CRITICAL" || severity === "ERROR",
          priority:
            severity === "FATAL_OR_CRITICAL"
              ? "critical"
              : severity === "ERROR"
                ? "high"
                : severity === "WARNING"
                  ? "low"
                  : "none",
          inference_ms: 20 + Math.random() * 60,
          all_probabilities: probs,
        }),
      400 + Math.random() * 400,
    ),
  );
}
