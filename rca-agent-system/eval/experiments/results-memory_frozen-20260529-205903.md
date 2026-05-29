# RCA pipeline evaluation

- Variant (ablation): **memory_frozen**
- Scenarios: **15** (12 in-domain, 3 OOD)
- Mean latency: **29.558s** (p95 ≈ 35.093s)
- Mean Gemini tokens / scenario: **21422.9**
- Mean top retrieval similarity: **0.586**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=12, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=11, partial=4, miss=0 (exact-or-partial = **1.0**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent_frozen | 9.29 | 8035.133 |
| reasoning_agent | 7.225 | 3288.467 |
| reflection_agent | 7.133 | 7496.8 |
| retrieval_agent | 5.909 | 2602.467 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7441 | 1 | hit | 26.349 | 20795 | — |
| redis-2 | exact | 0.75 | 0.5232 | 1 | hit | 32.126 | 22615 | — |
| jvm-oom-1 | exact | 0.80 | 0.8171 | 1 | hit | 29.127 | 21865 | — |
| jvm-oom-2 | exact | 1.00 | 0.7046 | 1 | hit | 28.784 | 21923 | — |
| deadlock-1 | partial | 0.40 | 0.6645 | 1 | hit | 33.955 | 21917 | — |
| deadlock-2 | exact | 0.75 | 0.5881 | 1 | hit | 29.857 | 21766 | — |
| upstream-1 | exact | 1.00 | 0.7757 | 1 | hit | 34.66 | 21799 | — |
| upstream-2 | exact | 0.80 | 0.3429 | 1 | hit | 35.093 | 21585 | — |
| tls-1 | partial | 0.60 | 0.7171 | 1 | hit | 27.239 | 20826 | — |
| tls-2 | exact | 0.75 | 0.659 | 1 | hit | 27.705 | 21737 | — |
| disk-1 | partial | 0.50 | 0.7839 | 1 | hit | 28.392 | 20744 | — |
| disk-2 | partial | 0.33 | 0.5851 | 1 | hit | 24.398 | 20278 | — |
| ood-dns | exact | 0.67 | 0.2841 | — | OOD | 24.632 | 20363 | — |
| ood-rate-limit | exact | 1.00 | 0.2891 | — | OOD | 29.084 | 21333 | — |
| ood-feature-flag | exact | 1.00 | 0.3142 | — | OOD | 31.971 | 21797 | — |
