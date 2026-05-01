import type {
  ClassifyResponse,
  GenerateLogsRequest,
  GenerateLogsResponse,
  Severity,
} from "@/lib/types";

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

export async function generateLogs(
  req: GenerateLogsRequest = {},
  signal?: AbortSignal,
): Promise<GenerateLogsResponse> {
  if (USE_MOCK) return mockGenerateLogs(req);
  return jsonFetch<GenerateLogsResponse>(`${CLASSIFIER_URL}/generate-logs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
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

const MOCK_TEMPLATES: Record<Severity, string[]> = {
  NORMAL: [
    "INFO  HTTP 200 GET /api/health",
    "INFO  Cache hit ratio: 92.4%",
    "DEBUG Connection pool: 12/50 active",
    "INFO  HTTP 200 POST /api/orders/{id}",
  ],
  WARNING: [
    "WARN  Slow query (1.2s): SELECT * FROM events WHERE ...",
    "WARN  Deprecated endpoint /v1/users hit 14 times in last 5m",
    "WARN  Retry attempt 2/3 for upstream 'inventory'",
  ],
  ERROR: [
    "ERROR HTTP 500 POST /api/orders \u2014 IntegrityError",
    "ERROR Pod OOMKilled: order-processor exceeded memory limit",
    "ERROR Connection refused to redis://10.0.1.100:6379",
  ],
  FATAL_OR_CRITICAL: [
    "FATAL Cascading failure: 10 dependent services unreachable",
    "FATAL Unrecoverable database corruption detected",
    "FATAL Out of memory \u2014 process killed by OOM killer",
  ],
};

function mockGenerateLogs(
  req: GenerateLogsRequest,
): Promise<GenerateLogsResponse> {
  const profile = req.profile ?? "mixed";
  const numLines = req.num_lines ?? 10;
  // Pick a target severity from the profile.
  let intended: Severity = "NORMAL";
  if (profile === "fatal") intended = "FATAL_OR_CRITICAL";
  else if (profile === "error") intended = "ERROR";
  else if (profile === "warning") intended = "WARNING";
  else if (profile === "normal") intended = "NORMAL";
  else {
    // mixed \u2014 weighted random
    const r = Math.random();
    if (r < 0.05) intended = "FATAL_OR_CRITICAL";
    else if (r < 0.25) intended = "ERROR";
    else if (r < 0.45) intended = "WARNING";
    else intended = "NORMAL";
  }
  const pool = MOCK_TEMPLATES[intended];
  const lines: string[] = [];
  const now = new Date();
  for (let i = 0; i < numLines; i++) {
    const ts = new Date(now.getTime() + i * 1000)
      .toISOString()
      .slice(0, 19)
      .replace("T", " ");
    lines.push(`${ts} ${pool[i % pool.length]}`);
  }
  return new Promise((r) =>
    setTimeout(
      () =>
        r({
          log_chunk: lines.join("\n"),
          intended_severity: intended,
          num_lines: numLines,
        }),
      150 + Math.random() * 150,
    ),
  );
}
