---
incident_id: db-pool-exhaustion-001
title: API requests hung after the DB connection pool was exhausted by a leak
severity: FATAL_OR_CRITICAL
resolution: Fixed the code path to release connections in a `finally` block; added a pool-usage gauge and alert at 90% utilization
root_cause: A recently-added report-export code path opened a DB connection but never returned it to the pool on the error branch
tags: database,connection-pool,leak,timeout,postgres
---

API latency spiked and then most endpoints started returning 504s. The
application logs showed `TimeoutError: QueuePool limit of size 20 overflow 10
reached, connection timed out`. A newly-shipped report-export feature opened a
raw connection for a long-running query but, on the error/cancellation branch,
returned early without closing it. Under normal load this leaked one
connection every few minutes; over a few hours the pool was fully exhausted
and every other request -- unrelated to reports -- was starved waiting for a
connection that would never free up.

## Log excerpt
WARN  DB pool utilization at 18/20 connections (usage climbing steadily)
ERROR TimeoutError: QueuePool limit of size 20 overflow 10 reached, connection timed out
FATAL 92% of API requests returned 504 in the last 5 minutes

## What worked
- Querying `pg_stat_activity` showed dozens of idle-in-transaction connections
  all originating from the report-export code path, which pointed straight at
  the leak.
- Deploying the `finally`-block fix and watching pool utilization drop back to
  baseline within minutes confirmed the root cause.

## What did NOT help
- Restarting the application servers (freed the pool immediately, but it
  refilled with leaked connections again within the hour since the bug was
  still in the code).
- Increasing the pool size (bought a bit more runway before exhaustion, but
  did not stop the underlying leak).
