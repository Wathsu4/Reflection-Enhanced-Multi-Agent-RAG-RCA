/**
 * Client for the evaluation-console API (`/eval/*`) exposed by the agent
 * service (`rca-agent-system`). Mirrors `agents.ts` / `classifier.ts`:
 * typed responses, named error classes, a shared `fetchJson`, and a
 * `__test__` export so unit tests can pin the resolved config without
 * fighting env vars.
 *
 * Long-running jobs are observed by **polling** `getJob` (see
 * `useExperimentRun`), not SSE -- the per-scenario cadence is slow enough
 * that polling is simpler and reconnection-safe.
 */

const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";

// -------------------- shared types (mirror the backend pydantic models) --------------------

export type ExperimentStatus = "runnable" | "planned";
export type ScriptName = "evaluate" | "memory_evolution";

export interface ParamSpec {
  name: string;
  label: string;
  kind: "int" | "bool";
  cli_flag: string;
  default: number | boolean;
  help: string;
  minimum: number | null;
  maximum: number | null;
}

export interface Experiment {
  id: string;
  title: string;
  summary: string;
  description_plain: string;
  description_technical: string;
  rq_tags: string[];
  family: string;
  status: ExperimentStatus;
  script: ScriptName | null;
  base_args: string[];
  params: ParamSpec[];
  outputs_glob: string;
  gemini: boolean;
  gemini_cost_note: string;
  expected_runtime: string;
}

export interface JobProgress {
  done: number;
  total: number;
  phase: string;
}

export type JobStatus = "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  experiment_id: string;
  title: string;
  params: Record<string, number | boolean>;
  status: JobStatus;
  progress: JobProgress;
  created_ts: number;
  started_ts: number | null;
  finished_ts: number | null;
  returncode: number | null;
  error: string | null;
  summary: Record<string, unknown> | null;
  result_files: string[];
  log_tail: string[];
}

export interface ResultEntry {
  timestamp_ts: number;
  size_bytes: number;
  json_path: string | null;
  markdown_path: string | null;
}

export interface ExperimentListResponse {
  experiments: Experiment[];
  busy: boolean;
  current_job_id: string | null;
}

export interface ExperimentDetailResponse {
  experiment: Experiment;
  results: ResultEntry[];
  busy: boolean;
  current_job_id: string | null;
}

export interface ResultFileResponse {
  path: string;
  format: "json" | "markdown";
  content: string;
}

// -------------------- error classes --------------------

/** Network-level failures: DNS, connection refused, CORS, abort. */
export class EvalNetworkError extends Error {
  constructor(message: string, public cause?: unknown) {
    super(message);
    this.name = "EvalNetworkError";
  }
}

/** Non-2xx HTTP responses from the eval API. */
export class EvalHttpError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
  ) {
    super(message);
    this.name = "EvalHttpError";
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

async function safeFetch(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    throw new EvalNetworkError(`Could not reach agent service at ${url}`, err);
  }
}

async function fetchJson<T>(url: string, init: RequestInit): Promise<T> {
  const res = await safeFetch(url, init);
  if (!res.ok) {
    const detail = await readDetail(res);
    const friendly =
      res.status >= 500
        ? `Eval service error (${res.status})`
        : `Eval request rejected (${res.status})`;
    throw new EvalHttpError(res.status, friendly, detail);
  }
  try {
    return (await res.json()) as T;
  } catch (err) {
    throw new EvalHttpError(
      res.status,
      "Eval service returned invalid JSON",
      err instanceof Error ? err.message : undefined,
    );
  }
}

// -------------------- URL builders --------------------

function experimentsUrl(): string {
  return `${AGENT_URL}/eval/experiments`;
}
function experimentUrl(id: string): string {
  return `${AGENT_URL}/eval/experiments/${encodeURIComponent(id)}`;
}
function runUrl(id: string): string {
  return `${experimentUrl(id)}/run`;
}
function jobUrl(jobId: string): string {
  return `${AGENT_URL}/eval/jobs/${encodeURIComponent(jobId)}`;
}
function resultUrl(relPath: string): string {
  // The path can contain a slash ("experiments/results-...json"); encode
  // each segment but keep the separators.
  const encoded = relPath.split("/").map(encodeURIComponent).join("/");
  return `${AGENT_URL}/eval/results/${encoded}`;
}

// -------------------- public API --------------------

export async function listExperiments(
  signal?: AbortSignal,
): Promise<ExperimentListResponse> {
  return fetchJson<ExperimentListResponse>(experimentsUrl(), {
    method: "GET",
    signal,
  });
}

export async function getExperiment(
  id: string,
  signal?: AbortSignal,
): Promise<ExperimentDetailResponse> {
  return fetchJson<ExperimentDetailResponse>(experimentUrl(id), {
    method: "GET",
    signal,
  });
}

export async function runExperiment(
  id: string,
  params: Record<string, number | boolean> = {},
): Promise<Job> {
  return fetchJson<Job>(runUrl(id), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return fetchJson<Job>(jobUrl(jobId), { method: "GET", signal });
}

export async function cancelJob(
  jobId: string,
): Promise<{ cancelled: boolean; job_id: string }> {
  return fetchJson<{ cancelled: boolean; job_id: string }>(
    `${jobUrl(jobId)}/cancel`,
    { method: "POST" },
  );
}

export async function getResult(
  relPath: string,
  signal?: AbortSignal,
): Promise<ResultFileResponse> {
  return fetchJson<ResultFileResponse>(resultUrl(relPath), {
    method: "GET",
    signal,
  });
}

// -------------------- test exports --------------------

export const __test__ = {
  AGENT_URL,
  experimentsUrl,
  experimentUrl,
  runUrl,
  jobUrl,
  resultUrl,
};
