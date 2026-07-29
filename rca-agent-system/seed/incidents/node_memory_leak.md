---
incident_id: node-memory-leak-001
title: Notification worker degraded over days from a slow memory leak
severity: ERROR
resolution: Fixed the listener leak and added a process-level RSS alert plus a weekly scheduled restart as a safety net
root_cause: An event listener was added on every job but never removed, so listeners (and their closures) accumulated for the life of the process
tags: nodejs,memory-leak,worker,event-listener,degradation
---

The notification worker's response latency crept up over about four days
until it was taking 10x longer to process each job, then started crashing
with `FATAL ERROR: Reached heap limit, Allocation failed - JavaScript heap out
of memory` roughly once a day. Process RSS grew steadily and never dropped
back down after garbage collection, unlike a normal sawtooth memory pattern.
A heap snapshot comparison between two points a day apart showed thousands of
retained `EventEmitter` listeners: a recent change attached a `once` listener
to a shared emitter inside the per-job handler but on an error path skipped
the code that removed it, so listeners (and everything they closed over)
piled up for the process's entire lifetime instead of being garbage collected
per job.

## Log excerpt
WARN  Process RSS: 1.8GB (baseline: 250MB), climbing steadily over 4 days
WARN  MaxListenersExceededWarning: Possible EventEmitter memory leak detected
FATAL JavaScript heap out of memory: Reached heap limit, Allocation failed

## What worked
- Two heap snapshots taken 24 hours apart, diffed in Chrome DevTools, showed
  the exact retainer path: thousands of orphaned listener closures.
- The `MaxListenersExceededWarning` in the logs was an early, specific signal
  that pointed straight at `EventEmitter` usage rather than a generic leak.

## What did NOT help
- Restarting the process on a schedule masked the symptom for a while but the
  same slow climb resumed immediately after each restart.
- Increasing the container's memory limit only delayed the eventual OOM
  crash by about a day.
