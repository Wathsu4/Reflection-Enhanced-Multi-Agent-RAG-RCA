# RCA pipeline evaluation

- Variant (ablation): **memory_frozen**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **25.215s** (p95 ≈ 37.689s)
- Mean Gemini tokens / scenario: **21915.7**
- Mean top retrieval similarity: **0.582**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=12, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=11, partial=4, miss=0 (exact-or-partial = **1.0**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent_frozen | 7.8 | 7599.133 |
| reasoning_agent | 5.933 | 3203.8 |
| reflection_agent | 6.487 | 8463.333 |
| retrieval_agent | 4.995 | 2649.467 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7441 | 1 | hit | 21.981 | 21036 | — |
| redis-2 | exact | 0.75 | 0.567 | 1 | hit | 23.141 | 22118 | — |
| jvm-oom-1 | exact | 1.00 | 0.7767 | 1 | hit | 23.45 | 22728 | — |
| jvm-oom-2 | exact | 1.00 | 0.6886 | 1 | hit | 21.801 | 21262 | — |
| deadlock-1 | partial | 0.40 | 0.6677 | 1 | hit | 24.992 | 21967 | — |
| deadlock-2 | partial | 0.50 | 0.6299 | 1 | hit | 37.689 | 24886 | — |
| upstream-1 | exact | 1.00 | 0.7681 | 1 | hit | 28.667 | 22408 | — |
| upstream-2 | exact | 0.80 | 0.3459 | 1 | hit | 22.36 | 20828 | — |
| tls-1 | partial | 0.60 | 0.7171 | 1 | hit | 25.461 | 21016 | — |
| tls-2 | exact | 0.75 | 0.6485 | 1 | hit | 22.673 | 21382 | — |
| disk-1 | partial | 0.50 | 0.7749 | 1 | hit | 22.064 | 22807 | — |
| disk-2 | exact | 0.67 | 0.5202 | 1 | hit | 21.407 | 20458 | — |
| ood-dns | exact | 0.67 | 0.292 | — | OOD | 23.03 | 20803 | — |
| ood-rate-limit | exact | 1.00 | 0.3171 | — | OOD | 33.885 | 23925 | — |
| ood-feature-flag | exact | 0.67 | 0.2745 | — | OOD | 25.62 | 21112 | — |
