# RCA pipeline evaluation

- Variant (ablation): **retrieval_only**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **0.672s** (p95 ≈ 0.724s)
- Mean top retrieval similarity: **0.636**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=12, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=1, partial=1, miss=13 (exact-or-partial = **0.133**)

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 0.80 | 0.8253 | 1 | hit | 0.454 | — | — |
| redis-2 | miss | 0.25 | 0.6672 | 1 | hit | 0.609 | — | — |
| jvm-oom-1 | miss | 0.20 | 0.7727 | 1 | hit | 0.696 | — | — |
| jvm-oom-2 | partial | 0.50 | 0.7289 | 1 | hit | 0.665 | — | — |
| deadlock-1 | miss | 0.20 | 0.7467 | 1 | hit | 0.686 | — | — |
| deadlock-2 | miss | 0.00 | 0.6237 | 1 | hit | 0.699 | — | — |
| upstream-1 | miss | 0.25 | 0.8098 | 1 | hit | 0.703 | — | — |
| upstream-2 | miss | 0.20 | 0.4828 | 1 | hit | 0.668 | — | — |
| tls-1 | miss | 0.00 | 0.7064 | 1 | hit | 0.689 | — | — |
| tls-2 | miss | 0.00 | 0.6993 | 1 | hit | 0.691 | — | — |
| disk-1 | miss | 0.25 | 0.7684 | 1 | hit | 0.695 | — | — |
| disk-2 | miss | 0.00 | 0.5967 | 1 | hit | 0.698 | — | — |
| ood-dns | miss | 0.00 | 0.3798 | — | OOD | 0.724 | — | — |
| ood-rate-limit | miss | 0.00 | 0.3277 | — | OOD | 0.7 | — | — |
| ood-feature-flag | miss | 0.00 | 0.4042 | — | OOD | 0.701 | — | — |
