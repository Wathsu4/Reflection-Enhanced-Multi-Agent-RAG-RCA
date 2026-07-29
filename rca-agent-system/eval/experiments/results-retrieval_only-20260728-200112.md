# RCA pipeline evaluation

- Variant (ablation): **retrieval_only**
- Scenarios: **31** (28 in-domain, 3 OOD)
- Mean latency: **0.061s** (p95 ≈ 0.097s)
- Mean top retrieval similarity: **0.681**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=28, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=3, partial=7, miss=21 (exact-or-partial = **0.323**)

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 0.80 | 0.8253 | 1 | hit | 0.137 | — | — |
| redis-2 | miss | 0.25 | 0.6672 | 1 | hit | 0.07 | — | — |
| jvm-oom-1 | miss | 0.20 | 0.7727 | 1 | hit | 0.059 | — | — |
| jvm-oom-2 | partial | 0.50 | 0.7289 | 1 | hit | 0.059 | — | — |
| deadlock-1 | miss | 0.20 | 0.7467 | 1 | hit | 0.057 | — | — |
| deadlock-2 | miss | 0.00 | 0.6237 | 1 | hit | 0.058 | — | — |
| upstream-1 | miss | 0.25 | 0.8098 | 1 | hit | 0.058 | — | — |
| upstream-2 | miss | 0.20 | 0.4828 | 1 | hit | 0.058 | — | — |
| tls-1 | miss | 0.00 | 0.7064 | 1 | hit | 0.057 | — | — |
| tls-2 | miss | 0.00 | 0.6993 | 1 | hit | 0.058 | — | — |
| disk-1 | miss | 0.25 | 0.7684 | 1 | hit | 0.059 | — | — |
| disk-2 | miss | 0.00 | 0.5967 | 1 | hit | 0.058 | — | — |
| ood-dns | miss | 0.00 | 0.4639 | — | OOD | 0.059 | — | — |
| ood-rate-limit | miss | 0.00 | 0.4614 | — | OOD | 0.058 | — | — |
| ood-feature-flag | miss | 0.00 | 0.4172 | — | OOD | 0.058 | — | — |
| k8s-oom-1 | partial | 0.40 | 0.8192 | 1 | hit | 0.059 | — | — |
| k8s-oom-2 | miss | 0.20 | 0.7327 | 1 | hit | 0.058 | — | — |
| kafka-lag-1 | partial | 0.40 | 0.756 | 1 | hit | 0.058 | — | — |
| kafka-lag-2 | miss | 0.20 | 0.6877 | 1 | hit | 0.058 | — | — |
| db-pool-1 | miss | 0.00 | 0.7079 | 1 | hit | 0.059 | — | — |
| db-pool-2 | miss | 0.00 | 0.7131 | 1 | hit | 0.059 | — | — |
| api-key-1 | partial | 0.60 | 0.747 | 1 | hit | 0.059 | — | — |
| api-key-2 | partial | 0.60 | 0.7812 | 1 | hit | 0.059 | — | — |
| cdn-stale-1 | exact | 0.80 | 0.6862 | 1 | hit | 0.058 | — | — |
| cdn-stale-2 | partial | 0.60 | 0.4729 | 1 | hit | 0.058 | — | — |
| lb-flap-1 | miss | 0.20 | 0.7046 | 1 | hit | 0.059 | — | — |
| lb-flap-2 | miss | 0.20 | 0.6945 | 1 | hit | 0.062 | — | — |
| node-leak-1 | miss | 0.20 | 0.7632 | 1 | hit | 0.059 | — | — |
| node-leak-2 | miss | 0.00 | 0.7735 | 1 | hit | 0.059 | — | — |
| dist-lock-1 | partial | 0.60 | 0.6609 | 1 | hit | 0.059 | — | — |
| dist-lock-2 | exact | 0.80 | 0.6256 | 1 | hit | 0.06 | — | — |
