---
incident_id: lb-health-check-flap-001
title: Load balancer marked healthy instances unhealthy under normal GC pauses
severity: ERROR
resolution: Relaxed the health-check timeout to 2s and unhealthy threshold to 3 consecutive failures, matching the service's real p99 response time
root_cause: A health-check timeout of 200ms was too aggressive for the service's occasional 300-400ms GC-pause response times
tags: load-balancer,health-check,capacity,latency,availability
---

Roughly a third of the fleet was cycling in and out of the load balancer's
healthy pool every few minutes, and overall error rate climbed to 8% during
the churn even though every instance was individually functioning correctly.
The health check used a 200ms timeout and marked an instance unhealthy after
a single failure. The service's garbage collector paused the process for
300-400ms every few minutes under normal load, which was enough to miss the
tight health-check window and get pulled from rotation -- right as the
remaining "healthy" instances absorbed the extra traffic and became more
likely to pause too, creating a feedback loop.

## Log excerpt
WARN  Instance i-0a1b2c marked UNHEALTHY (health check timeout after 200ms)
WARN  Instance i-0a1b2c marked HEALTHY again 45s later
ERROR Elevated 5xx rate (8.2%) correlated with rotating instance pool size

## What worked
- Overlaying the health-check failure timestamps with GC pause logs from the
  same instances showed a near-perfect match.
- Confirming the "unhealthy" instances served requests successfully via
  direct (bypassing the LB) requests during the flapping window.

## What did NOT help
- Adding more instances to the pool (churn continued at the same relative
  rate since the timeout was still too tight for any single instance).
- Restarting the flapping instances (a fresh instance paused for GC too,
  just on a different schedule).
