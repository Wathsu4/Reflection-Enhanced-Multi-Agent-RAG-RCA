# Memory-evolution evaluation

Pipeline variant (ablation): **none**

Ran the in-domain subset (28 scenarios) through the pipeline 1 time(s). Scores below are the dynamic `success_score` field maintained by the reflection + memory_update agents.

Expected pattern: incidents that the reasoning agent *correctly* leans on get boosted (>1.0); incidents retrieved but judged irrelevant get demoted (<1.0). All starting from the seed value of 1.0.

| incident_id | baseline | after run 1 |
|---|---|---|
| `api-key-expired-001` | 1.000 | 1.333 |
| `cdn-stale-cache-001` | 1.000 | 1.200 |
| `db-deadlock-001` | 1.000 | 1.231 |
| `db-pool-exhaustion-001` | 1.000 | 1.000 |
| `disk-full-log-001` | 1.000 | 1.200 |
| `distributed-lock-stale-001` | 1.000 | 1.000 |
| `jvm-oom-heap-001` | 1.000 | 1.091 |
| `k8s-oom-kill-001` | 1.000 | 1.221 |
| `kafka-consumer-lag-001` | 1.000 | 1.333 |
| `lb-health-check-flap-001` | 1.000 | 1.211 |
| `node-memory-leak-001` | 1.000 | 1.200 |
| `redis-conn-refused-001` | 1.000 | 1.333 |
| `tls-cert-expired-001` | 1.000 | 1.333 |
| `upstream-timeout-payments-001` | 1.000 | 1.333 |

**Drift summary (final vs baseline):** 12 incident(s) boosted, 0 demoted, 2 unchanged.

## Scenarios used

- `redis-1`
- `redis-2`
- `jvm-oom-1`
- `jvm-oom-2`
- `deadlock-1`
- `deadlock-2`
- `upstream-1`
- `upstream-2`
- `tls-1`
- `tls-2`
- `disk-1`
- `disk-2`
- `k8s-oom-1`
- `k8s-oom-2`
- `kafka-lag-1`
- `kafka-lag-2`
- `db-pool-1`
- `db-pool-2`
- `api-key-1`
- `api-key-2`
- `cdn-stale-1`
- `cdn-stale-2`
- `lb-flap-1`
- `lb-flap-2`
- `node-leak-1`
- `node-leak-2`
- `dist-lock-1`
- `dist-lock-2`
