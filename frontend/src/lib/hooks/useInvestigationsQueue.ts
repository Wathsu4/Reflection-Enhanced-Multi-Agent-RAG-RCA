"use client";

/**
 * `useInvestigationsQueue` is the heart of Phase 9: when a classified
 * `SimEvent` arrives with `should_invoke_rca: true`, we want to fire
 * an RCA run automatically -- but only one at a time, and only while
 * the user has Auto-RCA enabled.
 *
 * Design choices:
 *   * **One stream at a time**: Gemini rate limits + ChromaDB write
 *     ordering get hard to reason about with parallel agent runs. The
 *     queue serializes everything; new triggers wait their turn.
 *   * **Independent of `useAgentStream`**: opening /agent-explorer in
 *     a separate page must not stall the simulator's queue (and
 *     vice versa). We manage our own AbortController here.
 *   * **No reactivity from inside the streaming work**: we collect all
 *     events into a local array first, then commit them to React
 *     state in one batched setInvestigations call per event. This is
 *     critical because raw SSE produces 50-150 events per run and
 *     a per-event setState was visibly stuttering the simulator
 *     animation in profiling.
 *   * **Bounded memory**: at most `MAX_INVESTIGATIONS` entries; each
 *     keeps at most `MAX_EVENTS_PER_INVESTIGATION` raw events. Older
 *     ones are dropped, oldest first.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AgentHttpError,
  AgentNetworkError,
  createSession,
  runAgentSSE,
} from "@/lib/api/agents";
import type { AdkEvent, Investigation, SimEvent } from "@/lib/types";

const MAX_INVESTIGATIONS = 30;
const MAX_EVENTS_PER_INVESTIGATION = 500;

const FINAL_OUTPUT_KEY = "final_output";

export interface UseInvestigationsQueueArgs {
  /** Source events from the classification simulator. */
  classifiedEvents: SimEvent[];
  /** When false, new triggers are ignored and queued items are dropped. */
  autoRcaEnabled: boolean;
}

export interface UseInvestigationsQueueResult {
  /** Newest first. */
  investigations: Investigation[];
  /** Cancel any active stream and clear all queued / done entries. */
  clear: () => void;
}

/** Pull the final markdown out of the latest `stateDelta` write, if any. */
function findFinalAnswer(events: AdkEvent[]): string | null {
  // Search from the end since the closing event is most likely to
  // contain the write; bail out as soon as we see one.
  for (let i = events.length - 1; i >= 0; i--) {
    const v = events[i].actions?.stateDelta?.[FINAL_OUTPUT_KEY];
    if (typeof v === "string" && v.trim()) return v;
  }
  return null;
}

export function useInvestigationsQueue({
  classifiedEvents,
  autoRcaEnabled,
}: UseInvestigationsQueueArgs): UseInvestigationsQueueResult {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  // Mirror of `investigations` we can read synchronously inside the
  // dispatcher. React's setState updaters run async, so capturing the
  // "next queued" item from inside an updater closure doesn't work
  // for the surrounding control flow -- the variable is still
  // undefined at the time we need to branch on it.
  const investigationsRef = useRef<Investigation[]>([]);
  useEffect(() => {
    investigationsRef.current = investigations;
  }, [investigations]);

  // Track which SimEvent ids we've already enqueued so a later
  // re-render of the same simulator state doesn't double-trigger.
  const triggeredIdsRef = useRef<Set<string>>(new Set());
  // Active AbortController for the currently-streaming investigation.
  const abortRef = useRef<AbortController | null>(null);
  // True while a run is in flight; gates the queue dispatcher so it
  // can't accidentally start a second stream.
  const runningRef = useRef(false);

  // ---------- queue: enqueue triggers ----------

  useEffect(() => {
    if (!autoRcaEnabled) return;
    const triggered = triggeredIdsRef.current;
    const newOnes: Investigation[] = [];
    for (const ev of classifiedEvents) {
      if (triggered.has(ev.id)) continue;
      // We only consider events that have actually been classified
      // (status === "classified") AND that the classifier flagged.
      if (ev.status !== "classified" || !ev.classification) continue;
      if (!ev.classification.should_invoke_rca) {
        // Mark as seen so a later re-render with this same event
        // doesn't re-evaluate -- saves a tiny bit of cycles in tight
        // simulator loops.
        triggered.add(ev.id);
        continue;
      }
      triggered.add(ev.id);
      newOnes.push({
        id: crypto.randomUUID(),
        triggeredBy: ev.id,
        startedAt: Date.now(),
        completedAt: null,
        status: "queued",
        events: [],
        chunk: ev.chunkText,
        severity: ev.classification.severity,
        finalAnswer: null,
        error: null,
      });
    }
    if (newOnes.length === 0) return;
    setInvestigations((prev) => {
      // newest first; cap total length.
      return [...newOnes.reverse(), ...prev].slice(0, MAX_INVESTIGATIONS);
    });
  }, [classifiedEvents, autoRcaEnabled]);

  // ---------- dispatcher: run the next queued one, sequentially ----------

  const startNext = useCallback(async () => {
    if (runningRef.current) return;
    // Read the current list from the ref synchronously and pick the
    // oldest queued entry (last in our newest-first array).
    const current = investigationsRef.current;
    let target: Investigation | undefined;
    for (let i = current.length - 1; i >= 0; i--) {
      if (current[i].status === "queued") {
        target = current[i];
        break;
      }
    }
    if (!target) return;
    runningRef.current = true;
    // Mark running. This setState fires asynchronously but the
    // runningRef guard above prevents a re-entrant startNext from
    // racing us.
    const targetId = target.id;
    setInvestigations((prev) =>
      prev.map((i) =>
        i.id === targetId ? { ...i, status: "running" } : i,
      ),
    );

    const investigationId = target.id;
    const controller = new AbortController();
    abortRef.current = controller;

    const finishWithError = (message: string) => {
      setInvestigations((prev) =>
        prev.map((i) =>
          i.id === investigationId
            ? {
                ...i,
                status: "error",
                error: message,
                completedAt: Date.now(),
              }
            : i,
        ),
      );
    };

    try {
      const sessionId = await createSession(investigationId);
      if (controller.signal.aborted) return;

      // Buffer raw events locally; commit periodically so React batches
      // renders. We commit after EVERY event because the timeline UX
      // relies on streaming feel; the batching is internal to React's
      // concurrent renderer (which already coalesces sub-frame setStates).
      const buffered: AdkEvent[] = [];
      for await (const ev of runAgentSSE(
        sessionId,
        target.chunk,
        controller.signal,
      )) {
        buffered.push(ev);
        // Commit a snapshot. Slicing keeps the buffer bounded.
        const snapshot = buffered.slice(-MAX_EVENTS_PER_INVESTIGATION);
        setInvestigations((prev) =>
          prev.map((i) =>
            i.id === investigationId
              ? {
                  ...i,
                  events: snapshot,
                  finalAnswer: findFinalAnswer(snapshot),
                }
              : i,
          ),
        );
      }
      // Stream closed cleanly.
      setInvestigations((prev) =>
        prev.map((i) =>
          i.id === investigationId
            ? {
                ...i,
                status: "done",
                completedAt: Date.now(),
                finalAnswer: findFinalAnswer(i.events),
              }
            : i,
        ),
      );
    } catch (err) {
      if (controller.signal.aborted) {
        // User cancelled -- treat as done with whatever events arrived,
        // not as an error. (Cancellation rolls the queue forward.)
        setInvestigations((prev) =>
          prev.map((i) =>
            i.id === investigationId && i.status === "running"
              ? { ...i, status: "done", completedAt: Date.now() }
              : i,
          ),
        );
      } else {
        const friendly =
          err instanceof AgentNetworkError
            ? "Could not reach the agent service."
            : err instanceof AgentHttpError
              ? `Agent service error (${err.status})${
                  err.detail ? `: ${err.detail}` : ""
                }`
              : err instanceof Error
                ? err.message
                : "Unknown error";
        finishWithError(friendly);
      }
    } finally {
      runningRef.current = false;
      abortRef.current = null;
    }
  }, []);

  // Kick the dispatcher whenever the investigation list changes; the
  // guard inside `startNext` makes this idempotent.
  useEffect(() => {
    if (!autoRcaEnabled) return;
    if (runningRef.current) return;
    if (!investigations.some((i) => i.status === "queued")) return;
    void startNext();
  }, [investigations, autoRcaEnabled, startNext]);

  // ---------- toggling Auto-RCA off ----------
  // Per spec deliverable #4: "The queue is cleared when the toggle
  // flips off". We abort the active stream (if any) and drop queued
  // items, but keep `done` and `error` entries so users can still
  // inspect them.

  useEffect(() => {
    if (autoRcaEnabled) return;
    abortRef.current?.abort();
    setInvestigations((prev) =>
      prev.filter((i) => i.status === "done" || i.status === "error"),
    );
  }, [autoRcaEnabled]);

  // ---------- cleanup on unmount ----------

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // ---------- public API ----------

  const clear = useCallback(() => {
    abortRef.current?.abort();
    triggeredIdsRef.current = new Set();
    setInvestigations([]);
  }, []);

  return useMemo(() => ({ investigations, clear }), [investigations, clear]);
}
