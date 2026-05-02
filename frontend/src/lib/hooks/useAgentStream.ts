"use client";

/**
 * `useAgentStream` is the central client-side state machine for a
 * live RCA run.
 *
 * Why it exists: ADK's `/run_sse` produces 50-150 fine-grained events
 * for a single 4-stage pipeline run. Components want a coarse view --
 * "what is each sub-agent doing right now" -- not the raw firehose.
 * The hook subscribes to the SSE generator and aggregates events into:
 *
 *   * `events` -- the raw stream, in order, useful for a debug view.
 *   * `groups` -- one entry per sub-agent author with text, tool
 *     invocations, and a completion flag. This is what the timeline
 *     component renders.
 *   * `finalMarkdown` -- the markdown-formatted summary written by the
 *     final agent (memory_update_agent under the current pipeline) via
 *     its `output_key`. Convenience for the result card.
 *
 * The hook is purely client-side and self-contained: no react-query,
 * no global store. Calling `run(message)` aborts any prior run.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AgentHttpError,
  AgentNetworkError,
  createSession,
  runAgentSSE,
} from "@/lib/api/agents";
import type {
  AdkEvent,
  AgentRunGroup,
  AgentToolInvocation,
} from "@/lib/types";

export type AgentRunStatus = "idle" | "streaming" | "done" | "error";

export interface AgentRunState {
  status: AgentRunStatus;
  /** Auto-generated session id used for this run; usable for replay later. */
  sessionId: string | null;
  /** Raw event log. */
  events: AdkEvent[];
  /** Aggregated, in arrival order of first-seen author. */
  groups: AgentRunGroup[];
  /** Markdown body emitted by the final agent (if completed). */
  finalMarkdown: string | null;
  error: string | null;
}

export interface UseAgentStreamResult extends AgentRunState {
  run: (message: string) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

/**
 * Reduce a raw event stream into per-author groups.
 *
 * Pure function (no React) so it's trivially testable and so we can
 * also use it for replay (rendering a saved session via `getSession`).
 */
export function aggregateEvents(events: AdkEvent[]): AgentRunGroup[] {
  // Use a Map for stable insertion order.
  const groups = new Map<string, AgentRunGroup>();
  // Track tool calls that haven't been matched to a response yet, by
  // call id, so a response event in a later group still finds its
  // call. (In practice ADK emits both under the same author.)
  const pendingByCallId = new Map<string, AgentToolInvocation>();

  for (const ev of events) {
    if (!ev.author) continue;
    let g = groups.get(ev.author);
    if (!g) {
      g = {
        author: ev.author,
        text: "",
        toolInvocations: [],
        isComplete: false,
        stateWrites: {},
        firstTs: ev.timestamp,
        lastTs: ev.timestamp,
      };
      groups.set(ev.author, g);
    }
    g.lastTs = ev.timestamp;

    const parts = ev.content?.parts ?? [];
    for (const part of parts) {
      if (typeof part.text === "string") {
        // ADK streams text as repeated `partial: true` events whose
        // payloads are NEW fragments, then sends one non-partial event
        // whose payload is the fully aggregated text. Concatenating
        // both would double the visible content -- so we only
        // accumulate the partials and let the final event REPLACE
        // them. This keeps the visible text truthful in either order
        // (replay reads the saved final event; live reads partials
        // until the closer arrives).
        if (ev.partial) {
          g.text += part.text;
        } else {
          g.text = part.text;
        }
      }
      if (part.functionCall) {
        const callId = part.functionCall.id ?? `${ev.id}-fc`;
        const inv: AgentToolInvocation = {
          callId,
          name: part.functionCall.name,
          args: part.functionCall.args,
        };
        // Avoid duplicate entries when ADK re-emits the same tool call
        // first as `partial` then as final. Match by callId.
        const existingIdx = g.toolInvocations.findIndex(
          (t) => t.callId === callId,
        );
        if (existingIdx >= 0) {
          g.toolInvocations[existingIdx] = {
            ...g.toolInvocations[existingIdx],
            ...inv,
          };
        } else {
          g.toolInvocations.push(inv);
          pendingByCallId.set(callId, inv);
        }
      }
      if (part.functionResponse) {
        const callId = part.functionResponse.id ?? "";
        const inv = pendingByCallId.get(callId);
        if (inv) {
          inv.response = part.functionResponse.response;
          pendingByCallId.delete(callId);
        } else {
          // Response without a recorded call -- still useful to show.
          g.toolInvocations.push({
            callId: callId || `${ev.id}-fr`,
            name: part.functionResponse.name,
            args: {},
            response: part.functionResponse.response,
          });
        }
      }
    }

    const stateDelta = ev.actions?.stateDelta;
    if (stateDelta && Object.keys(stateDelta).length > 0) {
      g.stateWrites = { ...g.stateWrites, ...stateDelta };
      // A non-empty stateDelta always closes the agent's turn (it is
      // emitted only after `output_key` fires).
      g.isComplete = true;
    }
    if (ev.partial === false) {
      g.isComplete = true;
    }
  }

  return Array.from(groups.values());
}

const FINAL_OUTPUT_KEY = "final_output";

function pickFinalMarkdown(groups: AgentRunGroup[]): string | null {
  // The final agent (memory_update_agent in Phase 7) writes its
  // markdown summary via `output_key="final_output"`. Pull that
  // explicitly so consumers don't have to know which agent name it is.
  for (const g of groups) {
    const v = g.stateWrites[FINAL_OUTPUT_KEY];
    if (typeof v === "string" && v.trim()) return v;
  }
  return null;
}

export function useAgentStream(): UseAgentStreamResult {
  const [state, setState] = useState<AgentRunState>({
    status: "idle",
    sessionId: null,
    events: [],
    groups: [],
    finalMarkdown: null,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight run when the host component unmounts. ADK
  // will keep churning Gemini calls otherwise, which costs tokens.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState({
      status: "idle",
      sessionId: null,
      events: [],
      groups: [],
      finalMarkdown: null,
      error: null,
    });
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const run = useCallback(async (message: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({
      status: "streaming",
      sessionId: null,
      events: [],
      groups: [],
      finalMarkdown: null,
      error: null,
    });

    try {
      const sessionId = await createSession();
      // If the user cancelled between createSession and the SSE start,
      // bail before opening the stream so we don't burn Gemini tokens.
      if (controller.signal.aborted) return;
      setState((s) => ({ ...s, sessionId }));

      for await (const ev of runAgentSSE(sessionId, message, controller.signal)) {
        setState((s) => {
          const events = [...s.events, ev];
          const groups = aggregateEvents(events);
          return {
            ...s,
            events,
            groups,
            finalMarkdown: pickFinalMarkdown(groups),
          };
        });
      }
      setState((s) => ({ ...s, status: "done" }));
    } catch (err) {
      if (controller.signal.aborted) {
        // User-initiated cancellation -- not an error.
        setState((s) => ({ ...s, status: "idle" }));
        return;
      }
      const friendly =
        err instanceof AgentNetworkError
          ? "Could not reach the agent service. Is it running on :8000?"
          : err instanceof AgentHttpError
            ? `Agent service error (${err.status})${err.detail ? `: ${err.detail}` : ""}`
            : err instanceof Error
              ? err.message
              : "Unknown error";
      setState((s) => ({ ...s, status: "error", error: friendly }));
    }
  }, []);

  return useMemo(
    () => ({ ...state, run, cancel, reset }),
    [state, run, cancel, reset],
  );
}
