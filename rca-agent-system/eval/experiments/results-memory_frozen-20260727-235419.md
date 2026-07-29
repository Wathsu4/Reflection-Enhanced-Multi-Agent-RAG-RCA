# RCA pipeline evaluation

- Variant (ablation): **memory_frozen**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **22.08s** (p95 ≈ 27.265s)
- Mean Gemini tokens / scenario: **20801.5**
- Mean top retrieval similarity: **0.573**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=12, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=10, partial=5, miss=0 (exact-or-partial = **1.0**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent_frozen | 6.452 | 7648.333 |
| reasoning_agent | 5.343 | 3167.133 |
| reflection_agent | 5.669 | 7389.333 |
| retrieval_agent | 4.616 | 2596.667 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7604 | 1 | hit | 22.575 | 20813 | — |
| redis-2 | exact | 0.75 | 0.5858 | 1 | hit | 25.749 | 21867 | — |
| jvm-oom-1 | partial | 0.60 | 0.8171 | 1 | hit | 20.309 | 21268 | — |
| jvm-oom-2 | exact | 1.00 | 0.6886 | 1 | hit | 20.398 | 21339 | — |
| deadlock-1 | exact | 1.00 | 0.6645 | 1 | hit | 23.089 | 21211 | — |
| deadlock-2 | exact | 0.75 | 0.6299 | 1 | hit | 22.34 | 21189 | — |
| upstream-1 | exact | 1.00 | 0.7757 | 1 | hit | 27.265 | 21349 | — |
| upstream-2 | exact | 1.00 | 0.3429 | 1 | hit | 21.907 | 20621 | — |
| tls-1 | partial | 0.60 | 0.718 | 1 | hit | 21.805 | 20537 | — |
| tls-2 | exact | 1.00 | 0.6485 | 1 | hit | 18.761 | 20162 | — |
| disk-1 | partial | 0.50 | 0.4709 | 1 | hit | 20.373 | 20356 | — |
| disk-2 | partial | 0.33 | 0.5851 | 1 | hit | 22.017 | 19628 | — |
| ood-dns | exact | 0.67 | 0.2841 | — | OOD | 21.523 | 20878 | — |
| ood-rate-limit | partial | 0.50 | 0.3406 | — | OOD | 21.174 | 20513 | — |
| ood-feature-flag | exact | 0.67 | 0.2806 | — | OOD | 21.913 | 20291 | — |
