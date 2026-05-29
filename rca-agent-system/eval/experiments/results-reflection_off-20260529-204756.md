# RCA pipeline evaluation

- Variant (ablation): **reflection_off**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **22.073s** (p95 ≈ 81.364s)
- Mean Gemini tokens / scenario: **11311.5**
- Mean top retrieval similarity: **0.591**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=12, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=8, partial=5, miss=2 (exact-or-partial = **0.867**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent | 9.495 | 5473.4 |
| reasoning_agent | 6.462 | 3225.067 |
| retrieval_agent | 6.116 | 2613.0 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7356 | 1 | hit | 16.223 | 11928 | — |
| redis-2 | exact | 0.75 | 0.6126 | 1 | hit | 18.052 | 12391 | — |
| jvm-oom-1 | miss | 0.00 | 0.8034 | 1 | hit | 18.135 | 9414 | — |
| jvm-oom-2 | exact | 1.00 | 0.6886 | 1 | hit | 17.27 | 11622 | — |
| deadlock-1 | partial | 0.40 | 0.6677 | 1 | hit | 18.282 | 11477 | — |
| deadlock-2 | partial | 0.50 | 0.6133 | 1 | hit | 16.526 | 11346 | — |
| upstream-1 | miss | 0.00 | 0.7757 | 1 | hit | 15.492 | 8543 | — |
| upstream-2 | partial | 0.60 | 0.4135 | 1 | hit | 16.188 | 11616 | — |
| tls-1 | partial | 0.60 | 0.7171 | 1 | hit | 16.434 | 11234 | — |
| tls-2 | exact | 1.00 | 0.6621 | 1 | hit | 81.364 | 12028 | — |
| disk-1 | partial | 0.50 | 0.7445 | 1 | hit | 24.634 | 12124 | — |
| disk-2 | exact | 0.67 | 0.5214 | 1 | hit | 21.554 | 11108 | — |
| ood-dns | exact | 0.67 | 0.2963 | — | OOD | 17.006 | 11557 | — |
| ood-rate-limit | exact | 1.00 | 0.3038 | — | OOD | 16.589 | 11465 | — |
| ood-feature-flag | exact | 1.00 | 0.3076 | — | OOD | 17.343 | 11819 | — |
