import type { ClassifyResponse } from "@/lib/types";

const CLASSIFIER_URL = process.env.NEXT_PUBLIC_CLASSIFIER_URL;
const USE_MOCK = !CLASSIFIER_URL; // Phase 1: no env var set → mock

export async function classify(logChunk: string): Promise<ClassifyResponse> {
  if (USE_MOCK) return mockClassify(logChunk);

  const res = await fetch(`${CLASSIFIER_URL}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ log_chunk: logChunk }),
  });
  if (!res.ok) throw new Error(`Classifier error: ${res.status}`);
  return res.json();
}

// Naive keyword-based mock. Good enough to exercise the UI.
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
