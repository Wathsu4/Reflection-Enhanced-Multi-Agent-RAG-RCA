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

// -------------------- ADK event types --------------------
//
// These mirror the wire shape of `/run_sse` events as emitted by Google
// ADK 1.32.x. Field names are camelCase (NOT snake_case as a previous
// version of this file incorrectly assumed) and verified empirically
// against a live pipeline run.
//
// We only declare the fields we actually consume; ADK adds many others
// (thoughtSignature, usageMetadata, modelVersion, ...) that we don't
// care about, and we deliberately don't list them so the type stays
// trim and forward-compatible.

export interface AdkFunctionCall {
  /** Stable id correlating a call to its later response event. */
  id?: string;
  name: string;
  args: Record<string, unknown>;
}

export interface AdkFunctionResponse {
  id?: string;
  name: string;
  response: unknown;
}

export interface AdkEventPart {
  text?: string;
  functionCall?: AdkFunctionCall;
  functionResponse?: AdkFunctionResponse;
}

export interface AdkEventActions {
  /**
   * When an Agent declares `output_key="foo"`, ADK writes
   * `session.state["foo"]` at the end of that agent's turn and surfaces
   * the write here. We use this as the authoritative "this agent just
   * finished" signal in the timeline.
   */
  stateDelta?: Record<string, unknown>;
}

export interface AdkEvent {
  id: string;
  /** The sub-agent that produced this event (e.g. `retrieval_agent`). */
  author: string;
  /** Unix epoch seconds (float). */
  timestamp: number;
  /**
   * Streaming chunk flag. When `true`, this event carries a partial
   * fragment of the agent's text and SHOULD be concatenated with later
   * partials sharing the same author until a non-partial event closes
   * the turn.
   */
  partial?: boolean;
  /** Single-message-per-turn invocation context for the whole pipeline. */
  invocationId?: string;
  content?: {
    parts: AdkEventPart[];
    role: "user" | "model";
  };
  actions?: AdkEventActions;
}

// -------------------- Aggregated view types --------------------
// Derived shapes our hooks produce from a raw event stream. Keeping
// them here means components don't need to know the wire format.

/** A single tool invocation (call + matching response, by id when available). */
export interface AgentToolInvocation {
  callId: string;
  name: string;
  args: Record<string, unknown>;
  response?: unknown;
}

/**
 * One automated RCA run launched by the simulator.
 *
 * Phase 9 introduces this. The shape mirrors `useAgentStream`'s result
 * but adds queue-status fields (`status`, `triggeredBy`, `chunk`) so
 * the simulator can render an investigations list independently of any
 * single live stream. The `events` array is the raw ADK event log we
 * later aggregate via `aggregateEvents` -- keeping it raw makes the
 * type cheap to serialize / replay.
 */
export interface Investigation {
  /** Same id used as ADK session id. */
  id: string;
  /** Id of the SimEvent (classification row) that triggered this RCA. */
  triggeredBy: string;
  /** Browser epoch ms when this Investigation entered the queue. */
  startedAt: number;
  /** Browser epoch ms when streaming finished, or null if not done. */
  completedAt: number | null;
  status: "queued" | "running" | "done" | "error";
  /** Raw ADK SSE events received so far (capped at 500 to bound memory). */
  events: AdkEvent[];
  /** The original log chunk that triggered the run. */
  chunk: string;
  /** Severity classified by the classifier upstream. */
  severity: Severity;
  /** Final markdown from `memory_update_agent` (output_key=final_output). */
  finalAnswer: string | null;
  /** Friendly error message when status is "error". */
  error: string | null;
}

/** All events from one sub-agent in one run, aggregated. */
export interface AgentRunGroup {
  /** Sub-agent name; matches `event.author`. */
  author: string;
  /** Concatenation of every text part across the partial chunks + final. */
  text: string;
  /** Tool calls + responses, in arrival order. */
  toolInvocations: AgentToolInvocation[];
  /** Truthy once a non-partial event closes the turn (or `stateDelta` fires). */
  isComplete: boolean;
  /** Any `output_key` writes captured from this agent's actions.stateDelta. */
  stateWrites: Record<string, unknown>;
  /** First and last event timestamps (epoch seconds). */
  firstTs: number;
  lastTs: number;
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
