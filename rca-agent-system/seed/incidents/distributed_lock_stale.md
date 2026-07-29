---
incident_id: distributed-lock-stale-001
title: Nightly export job stuck for 8 hours behind a lock its crashed owner never released
severity: FATAL_OR_CRITICAL
resolution: Added a TTL/lease to every distributed lock, and a watchdog job that force-releases locks whose owner process is no longer alive
root_cause: A worker crashed mid-job while holding a Redis-based distributed lock that had no expiry (TTL), so the lock was never released
tags: distributed-lock,redis,coordination,deadlock,worker
---

The nightly export job, which uses a Redis-based lock (`SETNX`) to ensure only
one worker runs it at a time, did not run at all for one night and then
appeared stuck "in progress" for 8+ hours the next. The previous night's
worker had crashed (an unrelated out-of-memory kill on the host) while
holding the lock key, and the lock was created without an expiry. Because no
TTL was set, Redis kept the key forever; every subsequent attempt to acquire
the lock failed instantly, and the job silently no-op'd rather than erroring
loudly, which is why it took a full day to notice.

## Log excerpt
INFO  export-job: attempting to acquire lock export:nightly
WARN  export-job: lock export:nightly already held, skipping run
ERROR export-job: lock export:nightly has been held for 28h -- likely stale

## What worked
- Running `TTL export:nightly` in Redis returned `-1` (no expiry set at all),
  which immediately explained why the lock could never expire on its own.
- Checking the presumed lock-holder's process logs showed it had been killed
  by the OOM killer hours earlier, well before the lock was manually cleared.

## What did NOT help
- Restarting the export job service (it correctly refused to run while the
  stale lock existed -- the fix had to be clearing the lock itself).
- Waiting, expecting the lock to expire on its own (it never would have,
  since no TTL had ever been set on the key).
