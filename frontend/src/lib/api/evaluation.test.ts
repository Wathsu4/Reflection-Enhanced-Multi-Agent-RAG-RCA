import { afterEach, describe, expect, it, vi } from "vitest";

import {
  EvalHttpError,
  EvalNetworkError,
  __test__,
  cancelJob,
  getJob,
  listExperiments,
  runExperiment,
} from "@/lib/api/evaluation";

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

describe("evaluation URL builders", () => {
  it("builds the experiments list URL", () => {
    expect(__test__.experimentsUrl()).toMatch(/\/eval\/experiments$/);
  });

  it("encodes the experiment id in the run URL", () => {
    expect(__test__.runUrl("ablation-no-rag")).toMatch(
      /\/eval\/experiments\/ablation-no-rag\/run$/,
    );
  });

  it("builds a job URL", () => {
    expect(__test__.jobUrl("abc123")).toMatch(/\/eval\/jobs\/abc123$/);
  });

  it("preserves path separators but encodes segments in result URLs", () => {
    const url = __test__.resultUrl("experiments/results-no_rag-1.json");
    expect(url).toMatch(/\/eval\/results\/experiments\/results-no_rag-1\.json$/);
  });
});

describe("listExperiments", () => {
  it("returns the parsed experiment list", async () => {
    mockFetchOk({ experiments: [{ id: "x" }], busy: false, current_job_id: null });
    const res = await listExperiments();
    expect(res.experiments).toHaveLength(1);
    expect(res.busy).toBe(false);
  });

  it("wraps network failures in EvalNetworkError", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("boom"));
    await expect(listExperiments()).rejects.toBeInstanceOf(EvalNetworkError);
  });
});

describe("runExperiment", () => {
  it("POSTs params and returns the job", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ id: "job1", status: "running" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const job = await runExperiment("ablation-no-rag", { limit: 2 });
    expect(job.id).toBe("job1");
    const [, init] = spy.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ params: { limit: 2 } });
  });

  it("raises EvalHttpError with detail on 409 busy", async () => {
    mockFetchStatus(409, { detail: "another evaluation job is running: xyz" });
    await expect(runExperiment("pipeline-full")).rejects.toMatchObject({
      name: "EvalHttpError",
      status: 409,
    });
  });
});

describe("getJob / cancelJob", () => {
  it("fetches a job by id", async () => {
    mockFetchOk({ id: "job1", status: "succeeded" });
    const job = await getJob("job1");
    expect(job.status).toBe("succeeded");
  });

  it("posts a cancel", async () => {
    mockFetchOk({ cancelled: true, job_id: "job1" });
    const res = await cancelJob("job1");
    expect(res.cancelled).toBe(true);
  });

  it("surfaces a 404 as EvalHttpError", async () => {
    mockFetchStatus(404, { detail: "unknown job" });
    await expect(getJob("nope")).rejects.toBeInstanceOf(EvalHttpError);
  });
});
