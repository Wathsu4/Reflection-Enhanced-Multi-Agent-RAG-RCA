/**
 * Unit tests for the classifier API client.
 *
 * The client is a thin wrapper around `fetch`, so we mock `global.fetch`
 * directly. This is simpler and faster than spinning up MSW for what amounts
 * to JSON request/response shaping and error mapping.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  classify,
  generateLogs,
  getClassifierHealth,
  ClassifierHttpError,
  ClassifierNetworkError,
  __test__,
} from "./classifier";

const SUCCESS_BODY = {
  severity: "ERROR",
  severity_id: 1,
  confidence: 0.92,
  should_invoke_rca: true,
  priority: "high",
  inference_ms: 42.1,
  all_probabilities: {
    FATAL_OR_CRITICAL: 0.04,
    ERROR: 0.92,
    WARNING: 0.03,
    NORMAL: 0.01,
  },
} as const;

const HEALTH_OK = {
  status: "ok",
  model_loaded: true,
  device: "mps",
};

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("classifier API client", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  describe("classify()", () => {
    it("posts the chunk and returns the parsed body on 2xx", async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(SUCCESS_BODY));

      const result = await classify("ERROR Connection refused");

      expect(result).toEqual(SUCCESS_BODY);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const [url, init] = fetchSpy.mock.calls[0]!;
      expect(url).toBe(`${__test__.CLASSIFIER_URL}/classify`);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        log_chunk: "ERROR Connection refused",
      });
    });

    it("throws ClassifierNetworkError when fetch rejects (service down)", async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError("Failed to fetch"));

      await expect(classify("anything")).rejects.toBeInstanceOf(
        ClassifierNetworkError,
      );
    });

    it("throws ClassifierHttpError(422) with detail on validation failure", async () => {
      // FastAPI 422 returns an array of validation errors.
      fetchSpy.mockResolvedValueOnce(
        jsonResponse(
          { detail: [{ msg: "log_chunk must not be empty" }] },
          { status: 422 },
        ),
      );

      const err = await classify("").catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ClassifierHttpError);
      const httpErr = err as ClassifierHttpError;
      expect(httpErr.status).toBe(422);
      expect(httpErr.detail).toContain("log_chunk must not be empty");
    });

    it("throws ClassifierHttpError(503) with detail on 5xx", async () => {
      fetchSpy.mockResolvedValueOnce(
        jsonResponse(
          { detail: "classifier not ready" },
          { status: 503 },
        ),
      );

      const err = await classify("ERROR ...").catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ClassifierHttpError);
      const httpErr = err as ClassifierHttpError;
      expect(httpErr.status).toBe(503);
      expect(httpErr.message).toMatch(/Classifier service error/i);
      expect(httpErr.detail).toBe("classifier not ready");
    });

    it("handles non-JSON 5xx responses gracefully (no crash, no detail)", async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response("internal server error", {
          status: 500,
          headers: { "content-type": "text/plain" },
        }),
      );

      const err = await classify("ERROR ...").catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ClassifierHttpError);
      expect((err as ClassifierHttpError).detail).toBeUndefined();
    });

    it("throws ClassifierHttpError if 200 response is not JSON", async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response("not json", {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

      const err = await classify("ERROR ...").catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ClassifierHttpError);
      expect((err as ClassifierHttpError).message).toMatch(/invalid JSON/i);
    });
  });

  describe("getClassifierHealth()", () => {
    it("GETs /health and returns the parsed body when healthy", async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(HEALTH_OK));

      const result = await getClassifierHealth();

      expect(result).toEqual(HEALTH_OK);
      const [url, init] = fetchSpy.mock.calls[0]!;
      expect(url).toBe(`${__test__.CLASSIFIER_URL}/health`);
      expect(init?.method).toBe("GET");
    });

    it("forwards the AbortSignal to fetch", async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(HEALTH_OK));
      const controller = new AbortController();

      await getClassifierHealth(controller.signal);

      const [, init] = fetchSpy.mock.calls[0]!;
      expect(init?.signal).toBe(controller.signal);
    });

    it("throws ClassifierNetworkError when service is unreachable", async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError("ECONNREFUSED"));

      await expect(getClassifierHealth()).rejects.toBeInstanceOf(
        ClassifierNetworkError,
      );
    });
  });

  describe("generateLogs()", () => {
    const GEN_BODY = {
      log_chunk: "2024-01-01 ERROR something broke",
      intended_severity: "ERROR" as const,
      num_lines: 1,
    };

    it("POSTs the request body to /generate-logs and returns the parsed body", async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(GEN_BODY));

      const result = await generateLogs({
        profile: "error",
        num_lines: 1,
        seed: 42,
      });

      expect(result).toEqual(GEN_BODY);
      const [url, init] = fetchSpy.mock.calls[0]!;
      expect(url).toBe(`${__test__.CLASSIFIER_URL}/generate-logs`);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        profile: "error",
        num_lines: 1,
        seed: 42,
      });
    });

    it("works with no arguments (backend defaults apply)", async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(GEN_BODY));

      await generateLogs();

      const [, init] = fetchSpy.mock.calls[0]!;
      expect(JSON.parse(String(init?.body))).toEqual({});
    });

    it("forwards the AbortSignal", async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(GEN_BODY));
      const controller = new AbortController();

      await generateLogs({ profile: "fatal" }, controller.signal);

      const [, init] = fetchSpy.mock.calls[0]!;
      expect(init?.signal).toBe(controller.signal);
    });

    it("throws ClassifierHttpError(400) with detail when backend rejects", async () => {
      fetchSpy.mockResolvedValueOnce(
        jsonResponse(
          { detail: "num_lines must be between 1 and 200" },
          { status: 400 },
        ),
      );

      const err = await generateLogs({ num_lines: 9999 }).catch(
        (e: unknown) => e,
      );

      expect(err).toBeInstanceOf(ClassifierHttpError);
      expect((err as ClassifierHttpError).status).toBe(400);
      expect((err as ClassifierHttpError).detail).toContain(
        "num_lines must be between",
      );
    });

    it("throws ClassifierNetworkError when fetch rejects", async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError("Failed to fetch"));

      await expect(generateLogs()).rejects.toBeInstanceOf(
        ClassifierNetworkError,
      );
    });
  });
});
