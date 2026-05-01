export type Severity = "FATAL_OR_CRITICAL" | "ERROR" | "WARNING" | "NORMAL";
export type Priority = "critical" | "high" | "low" | "none";
export type Profile = "normal" | "warning" | "error" | "fatal" | "mixed";

export interface GenerateLogsRequest {
  profile?: Profile;
  num_lines?: number;
  seed?: number;
}

/**
 * One row in the simulator's event feed. Lifecycle:
 * 1. Created with `status: "pending"` immediately after a chunk is generated.
 * 2. If auto-classify is on, transitions to `"classified"` (with `classification`
 *    populated) or `"error"` (with `classifyError` populated).
 * 3. If auto-classify is off, stays `"pending"` indefinitely.
 */
export interface SimEvent {
  id: string;
  timestamp: number;
  intendedSeverity: Severity;
  chunkText: string;
  numLines: number;
  classification: ClassifyResponse | null;
  classifyError: string | null;
  status: "pending" | "classified" | "error";
}

export interface ClassifyResponse {
  severity: Severity;
  severity_id: 0 | 1 | 2 | 3;
  confidence: number;
  should_invoke_rca: boolean;
  priority: Priority;
  inference_ms: number;
  all_probabilities: Record<Severity, number>;
}

export interface GenerateLogsResponse {
  log_chunk: string;
  intended_severity: Severity;
  num_lines: number;
}

// ADK event (partial — only fields we care about)
export interface AdkEvent {
  id: string;
  author: string; // agent name
  timestamp: number;
  content?: {
    parts: Array<{
      text?: string;
      function_call?: { name: string; args: Record<string, unknown> };
      function_response?: { name: string; response: unknown };
    }>;
    role: "user" | "model";
  };
  actions?: Record<string, unknown>;
}

export const SEVERITY_ORDER: Severity[] = [
  "FATAL_OR_CRITICAL",
  "ERROR",
  "WARNING",
  "NORMAL",
];

export const SEVERITY_COLORS: Record<Severity, string> = {
  FATAL_OR_CRITICAL: "bg-red-600 text-white",
  ERROR: "bg-orange-500 text-white",
  WARNING: "bg-yellow-500 text-black",
  NORMAL: "bg-green-600 text-white",
};
