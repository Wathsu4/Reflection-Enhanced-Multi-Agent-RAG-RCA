# Memory-evolution evaluation

Pipeline variant (ablation): **none**

Ran the in-domain subset (12 scenarios) through the pipeline 2 time(s). Scores below are the dynamic `success_score` field maintained by the reflection + memory_update agents.

Expected pattern: incidents that the reasoning agent *correctly* leans on get boosted (>1.0); incidents retrieved but judged irrelevant get demoted (<1.0). All starting from the seed value of 1.0.

| incident_id | baseline | after run 1 | after run 2 |
|---|---|---|---|
| `db-deadlock-001` | 1.000 | 0.800 | 0.600 |
| `disk-full-log-001` | 1.000 | 0.500 | 0.000 |
| `jvm-oom-heap-001` | 1.000 | 0.900 | 0.900 |
| `redis-conn-refused-001` | 1.000 | 1.200 | 1.450 |
| `tls-cert-expired-001` | 1.000 | 0.400 | 0.200 |
| `upstream-timeout-payments-001` | 1.000 | 0.600 | 0.300 |

**Drift summary (final vs baseline):** 1 incident(s) boosted, 5 demoted, 0 unchanged.

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
