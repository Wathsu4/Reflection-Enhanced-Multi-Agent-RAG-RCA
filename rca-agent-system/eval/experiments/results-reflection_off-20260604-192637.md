# RCA pipeline evaluation

- Variant (ablation): **reflection_off**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **28.869s** (p95 ≈ 33.803s)
- Mean Gemini tokens / scenario: **11544.3**
- Mean top retrieval similarity: **0.582**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=12, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=9, partial=5, miss=1 (exact-or-partial = **0.933**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent | 9.363 | 5706.133 |
| reasoning_agent | 8.709 | 3241.733 |
| retrieval_agent | 10.797 | 2596.4 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7378 | 1 | hit | 33.803 | 11990 | — |
| redis-2 | exact | 1.00 | 0.567 | 1 | hit | 28.229 | 11840 | — |
| jvm-oom-1 | partial | 0.60 | 0.7919 | 1 | hit | 29.036 | 12534 | — |
| jvm-oom-2 | exact | 0.75 | 0.6886 | 1 | hit | 27.901 | 12024 | — |
| deadlock-1 | partial | 0.40 | 0.6505 | 1 | hit | 27.142 | 10598 | — |
| deadlock-2 | miss | 0.25 | 0.5881 | 1 | hit | 27.061 | 11258 | — |
| upstream-1 | exact | 1.00 | 0.7888 | 1 | hit | 27.657 | 11037 | — |
| upstream-2 | partial | 0.60 | 0.3429 | 1 | hit | 30.274 | 11393 | — |
| tls-1 | exact | 0.80 | 0.725 | 1 | hit | 30.152 | 11189 | — |
| tls-2 | exact | 1.00 | 0.6376 | 1 | hit | 28.738 | 11967 | — |
| disk-1 | partial | 0.50 | 0.7526 | 1 | hit | 29.705 | 11370 | — |
| disk-2 | partial | 0.33 | 0.5717 | 1 | hit | 28.487 | 11345 | — |
| ood-dns | exact | 0.67 | 0.2841 | — | OOD | 28.265 | 11252 | — |
| ood-rate-limit | exact | 1.00 | 0.2941 | — | OOD | 28.51 | 11583 | — |
| ood-feature-flag | exact | 1.00 | 0.3037 | — | OOD | 28.076 | 11784 | — |
