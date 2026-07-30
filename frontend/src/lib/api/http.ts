/**
 * Shared HTTP plumbing for the typed service clients in this directory
 * (`agents.ts`, `classifier.ts`, `evaluation.ts`).
 *
 * Each client keeps its own named error classes -- callers and tests
 * discriminate on `AgentHttpError` vs `ClassifierHttpError` vs
 * `EvalHttpError` -- but the transport behaviour is identical: wrap
 * `fetch` so network failures are distinguishable from non-2xx
 * responses, and lift FastAPI's `{detail: ...}` payload into the error.
 * `createHttpClient` builds that behaviour around a client's own error
 * classes and message wording.
 */

/** Base for the per-service network error classes. */
export class ServiceNetworkError extends Error {
  constructor(message: string, public cause?: unknown) {
    super(message);
    this.name = "ServiceNetworkError";
  }
}

/** Base for the per-service HTTP error classes. */
export class ServiceHttpError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Parsed error payload from the server (FastAPI's `detail`), if any. */
    public detail?: string,
  ) {
    super(message);
    this.name = "ServiceHttpError";
  }
}

export type NetworkErrorCtor = new (message: string, cause?: unknown) => Error;
export type HttpErrorCtor = new (
  status: number,
  message: string,
  detail?: string,
) => Error;

export interface HttpClientConfig {
  NetworkError: NetworkErrorCtor;
  HttpError: HttpErrorCtor;
  /** Message for a `fetch` rejection (DNS, connection refused, CORS, abort). */
  unreachableMessage: (url: string) => string;
  /** Message for a 5xx response. */
  serverErrorMessage: (status: number) => string;
  /** Message for any other non-2xx response. */
  rejectedMessage: (status: number) => string;
  /** Message for a 2xx response whose body isn't JSON. */
  invalidJsonMessage: string;
}

export interface HttpClient {
  /** Wraps `fetch` so transport vs. server errors are distinguishable. */
  safeFetch(url: string, init: RequestInit): Promise<Response>;
  fetchJson<T>(url: string, init: RequestInit): Promise<T>;
}

/** Try to extract FastAPI-style `{detail: "..."}` from a failed response. */
export async function readDetail(res: Response): Promise<string | undefined> {
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

export function createHttpClient(config: HttpClientConfig): HttpClient {
  async function safeFetch(url: string, init: RequestInit): Promise<Response> {
    try {
      return await fetch(url, init);
    } catch (err) {
      // `fetch` only rejects on network failure / abort.
      throw new config.NetworkError(config.unreachableMessage(url), err);
    }
  }

  async function fetchJson<T>(url: string, init: RequestInit): Promise<T> {
    const res = await safeFetch(url, init);
    if (!res.ok) {
      const detail = await readDetail(res);
      const friendly =
        res.status >= 500
          ? config.serverErrorMessage(res.status)
          : config.rejectedMessage(res.status);
      throw new config.HttpError(res.status, friendly, detail);
    }
    try {
      return (await res.json()) as T;
    } catch (err) {
      throw new config.HttpError(
        res.status,
        config.invalidJsonMessage,
        err instanceof Error ? err.message : undefined,
      );
    }
  }

  return { safeFetch, fetchJson };
}
