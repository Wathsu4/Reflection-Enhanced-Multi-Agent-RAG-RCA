# RCA pipeline evaluation

- Variant (ablation): **memory_frozen**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **41.882s** (p95 ≈ 54.341s)
- Mean Gemini tokens / scenario: **18563.6**
- Mean top retrieval similarity: **0.577**
- Expected-incident retrieval recall (in-domain only): **0.917**
- Retrieval IR (in-domain, n=11, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=10, partial=2, miss=3 (exact-or-partial = **0.8**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent_frozen | 13.076 | 7912.615 |
| reasoning_agent | 8.395 | 3182.769 |
| reflection_agent | 11.075 | 7452.077 |
| retrieval_agent | 13.025 | 2489.133 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7441 | 1 | hit | 40.356 | 21032 | — |
| redis-2 | miss | 0.00 | — | — | miss | 51.596 | 963 | — |
| jvm-oom-1 | miss | 0.00 | 0.7867 | 1 | hit | 16.678 | 2784 | — |
| jvm-oom-2 | exact | 1.00 | 0.6886 | 1 | hit | 54.341 | 23832 | — |
| deadlock-1 | partial | 0.60 | 0.6504 | 1 | hit | 41.887 | 20040 | — |
| deadlock-2 | miss | 0.25 | 0.6133 | 1 | hit | 38.204 | 20626 | — |
| upstream-1 | exact | 0.75 | 0.6961 | 1 | hit | 41.524 | 20058 | — |
| upstream-2 | exact | 0.80 | 0.3459 | 1 | hit | 44.118 | 21588 | — |
| tls-1 | exact | 0.80 | 0.7282 | 1 | hit | 42.784 | 20701 | — |
| tls-2 | exact | 0.75 | 0.6485 | 1 | hit | 39.821 | 20383 | — |
| disk-1 | partial | 0.50 | 0.7538 | 1 | hit | 45.366 | 21762 | — |
| disk-2 | exact | 0.67 | 0.5202 | 1 | hit | 39.915 | 20792 | — |
| ood-dns | exact | 0.67 | 0.2732 | — | OOD | 46.315 | 21237 | — |
| ood-rate-limit | exact | 1.00 | 0.2955 | — | OOD | 45.846 | 22271 | — |
| ood-feature-flag | exact | 1.00 | 0.3305 | — | OOD | 39.484 | 20385 | — |
