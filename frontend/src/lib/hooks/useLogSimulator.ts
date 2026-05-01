"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { classify, generateLogs } from "@/lib/api/classifier";
import type { Profile, SimEvent } from "@/lib/types";

export interface SimulatorOptions {
  /** Backend `profile` parameter \u2014 controls the severity mix. */
  profile: Profile;
  /** Lines per generated chunk. 1\u2013200 (matches backend bound). */
  numLines: number;
  /** Gap between chunks, in milliseconds. */
  intervalMs: number;
  /** When true, each generated chunk is immediately classified. */
  autoClassify: boolean;
  /** Maximum number of events kept in the ring buffer. */
  maxEvents: number;
}

export const DEFAULT_OPTIONS: SimulatorOptions = {
  profile: "mixed",
  numLines: 10,
  intervalMs: 3_000,
  autoClassify: true,
  maxEvents: 50,
};

export interface UseLogSimulatorResult {
  events: SimEvent[];
  latest: SimEvent | null;
  running: boolean;
  /** Last error from generate-logs or classify (does not stop the loop). */
  lastError: Error | null;
  options: SimulatorOptions;
  start: (overrides?: Partial<SimulatorOptions>) => void;
  stop: () => void;
  clear: () => void;
  /** Update options live (takes effect on the next tick). */
  updateOptions: (overrides: Partial<SimulatorOptions>) => void;
}

/**
 * Drives the live-monitoring page.
 *
 * Each tick:
 *   1. POST /generate-logs (using the current `profile` + `numLines`).
 *   2. If `autoClassify`, POST /classify with the generated chunk.
 *   3. Prepend the resulting {@link SimEvent} to the ring buffer.
 *
 * Loop is self-scheduling via `setTimeout`; cancellation is cooperative
 * through a ref so that an in-flight request can early-exit on `stop()`.
 */
export function useLogSimulator(
  initial: Partial<SimulatorOptions> = {},
): UseLogSimulatorResult {
  const [events, setEvents] = useState<SimEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [lastError, setLastError] = useState<Error | null>(null);
  const [options, setOptions] = useState<SimulatorOptions>({
    ...DEFAULT_OPTIONS,
    ...initial,
  });

  const cancelRef = useRef<{ aborted: boolean }>({ aborted: true });
  const optionsRef = useRef<SimulatorOptions>(options);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Generation counter so a `clear()` invalidates any in-flight tick result.
  const generationRef = useRef(0);

  // Keep the ref in sync so the loop sees latest options without re-binding.
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const tick = useCallback(async () => {
    if (cancelRef.current.aborted) return;
    const myGeneration = generationRef.current;
    const opts = optionsRef.current;

    try {
      const gen = await generateLogs({
        profile: opts.profile,
        num_lines: opts.numLines,
      });

      if (cancelRef.current.aborted || myGeneration !== generationRef.current) {
        return;
      }

      const baseEvent: SimEvent = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Date.now(),
        intendedSeverity: gen.intended_severity,
        chunkText: gen.log_chunk,
        numLines: gen.num_lines,
        classification: null,
        classifyError: null,
        status: opts.autoClassify ? "pending" : "pending",
      };

      // Push the pending event so it appears in the feed immediately.
      setEvents((prev) =>
        [baseEvent, ...prev].slice(0, opts.maxEvents),
      );

      if (opts.autoClassify) {
        try {
          const result = await classify(gen.log_chunk);
          if (
            cancelRef.current.aborted ||
            myGeneration !== generationRef.current
          ) {
            return;
          }
          setEvents((prev) =>
            prev.map((e) =>
              e.id === baseEvent.id
                ? { ...e, classification: result, status: "classified" }
                : e,
            ),
          );
        } catch (err) {
          if (
            cancelRef.current.aborted ||
            myGeneration !== generationRef.current
          ) {
            return;
          }
          const message = err instanceof Error ? err.message : String(err);
          setEvents((prev) =>
            prev.map((e) =>
              e.id === baseEvent.id
                ? { ...e, classifyError: message, status: "error" }
                : e,
            ),
          );
          setLastError(err instanceof Error ? err : new Error(message));
        }
      }
    } catch (err) {
      // generateLogs failed \u2014 record the error but keep the loop alive so
      // the simulator recovers when the service comes back.
      if (
        cancelRef.current.aborted ||
        myGeneration !== generationRef.current
      ) {
        return;
      }
      setLastError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (
        !cancelRef.current.aborted &&
        myGeneration === generationRef.current
      ) {
        timeoutRef.current = setTimeout(tick, optionsRef.current.intervalMs);
      }
    }
  }, []);

  const start = useCallback(
    (overrides: Partial<SimulatorOptions> = {}) => {
      cancelRef.current.aborted = false;
      setOptions((prev) => {
        const next = { ...prev, ...overrides };
        optionsRef.current = next;
        return next;
      });
      setRunning(true);
      setLastError(null);
      // Fire the first tick immediately rather than waiting `intervalMs`.
      void tick();
    },
    [tick],
  );

  const stop = useCallback(() => {
    cancelRef.current.aborted = true;
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setRunning(false);
  }, []);

  const clear = useCallback(() => {
    generationRef.current += 1;
    setEvents([]);
    setLastError(null);
  }, []);

  const updateOptions = useCallback(
    (overrides: Partial<SimulatorOptions>) => {
      setOptions((prev) => {
        const next = { ...prev, ...overrides };
        optionsRef.current = next;
        return next;
      });
    },
    [],
  );

  // Stop the loop on unmount.
  useEffect(() => {
    return () => {
      cancelRef.current.aborted = true;
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return {
    events,
    latest: events[0] ?? null,
    running,
    lastError,
    options,
    start,
    stop,
    clear,
    updateOptions,
  };
}
