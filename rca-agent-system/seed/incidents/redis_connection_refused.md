---
incident_id: redis-conn-refused-001
title: Redis connection refused after network config change
severity: ERROR
root_cause: Firewall rule change blocked Redis port 6379 from the app subnet
resolution: Restored the firewall rule; added a monitoring probe specifically for Redis connectivity
tags: redis,network,connection,firewall,cache
---

Application hosts in the app subnet lost the ability to reach the Redis cluster at
10.0.1.100:6379 after a network team maintenance window. Symptoms: every batch
job that touched Redis failed within seconds of starting; cache-miss cascades
caused elevated read latency on the API. Recovery was manual restoration of the
previously-allowed firewall rule by the networking team.

## Log excerpt
ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused
ERROR Retry failed: Connection refused
ERROR Batch job #4521 failed: Cache unavailable

## What worked
- Correlated the start of errors with the network team's change ticket.
- Verified with `nc -zv 10.0.1.100 6379` from an app host (refused).

## What did NOT help
- Restarting the app process (the problem was external).
- Scaling the cache cluster (it was reachable from its own subnet).
