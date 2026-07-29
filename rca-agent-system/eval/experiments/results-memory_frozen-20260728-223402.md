# RCA pipeline evaluation

- Variant (ablation): **memory_frozen**
- Scenarios: **31** (28 in-domain, 3 OOD)
- Mean latency: **30.88s** (p95 ≈ 38.304s)
- Mean Gemini tokens / scenario: **28385.3**
- Mean top retrieval similarity: **0.639**
- Expected-incident retrieval recall (in-domain only): **0.964**
- Retrieval IR (in-domain, n=27, k=5): Recall@k=**1.0**, MRR=**1.0**, nDCG@k=**1.0**
- Keyword verdicts: exact=20, partial=11, miss=0 (exact-or-partial = **1.0**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent_frozen | 6.524 | 8417.839 |
| reasoning_agent | 6.558 | 3640.903 |
| reflection_agent | 12.465 | 13431.516 |
| retrieval_agent | 5.333 | 2895.065 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7441 | 1 | hit | 30.475 | 28847 | — |
| redis-2 | exact | 1.00 | 0.567 | 1 | hit | 32.038 | 28494 | — |
| jvm-oom-1 | exact | 0.80 | 0.7919 | 1 | hit | 33.062 | 32130 | — |
| jvm-oom-2 | exact | 1.00 | 0.6736 | 1 | hit | 30.688 | 28140 | — |
| deadlock-1 | partial | 0.40 | 0.6685 | 1 | hit | 27.763 | 27384 | — |
| deadlock-2 | partial | 0.50 | 0.6299 | 1 | hit | 31.034 | 26915 | — |
| upstream-1 | exact | 1.00 | 0.6845 | 1 | hit | 33.972 | 27005 | — |
| upstream-2 | partial | 0.60 | 0.4027 | 1 | hit | 30.535 | 26994 | — |
| tls-1 | exact | 0.80 | 0.7345 | 1 | hit | 28.918 | 26963 | — |
| tls-2 | exact | 0.75 | 0.6527 | 1 | hit | 28.895 | 28603 | — |
| disk-1 | partial | 0.50 | 0.738 | 1 | hit | 26.559 | 28024 | — |
| disk-2 | partial | 0.33 | 0.5242 | 1 | hit | 34.131 | 28804 | — |
| ood-dns | exact | 0.67 | 0.4121 | — | OOD | 28.266 | 25747 | — |
| ood-rate-limit | exact | 1.00 | 0.4095 | — | OOD | 32.876 | 28460 | — |
| ood-feature-flag | exact | 1.00 | 0.2906 | — | OOD | 28.586 | 26876 | — |
| k8s-oom-1 | exact | 0.80 | 0.5561 | 1 | hit | 38.524 | 33810 | — |
| k8s-oom-2 | partial | 0.60 | 0.6397 | 1 | hit | 38.158 | 30645 | — |
| kafka-lag-1 | partial | 0.60 | 0.7411 | 1 | hit | 35.247 | 32106 | — |
| kafka-lag-2 | exact | 1.00 | 0.7041 | 1 | hit | 28.731 | 28928 | — |
| db-pool-1 | exact | 0.80 | 0.6471 | 1 | hit | 30.759 | 29718 | — |
| db-pool-2 | exact | 1.00 | — | — | miss | 28.022 | 28650 | — |
| api-key-1 | exact | 1.00 | 0.7469 | 1 | hit | 25.036 | 28396 | — |
| api-key-2 | partial | 0.60 | 0.8163 | 1 | hit | 31.181 | 29224 | — |
| cdn-stale-1 | exact | 1.00 | 0.761 | 1 | hit | 35.393 | 29889 | — |
| cdn-stale-2 | exact | 0.80 | 0.4889 | 1 | hit | 32.472 | 29040 | — |
| lb-flap-1 | exact | 0.80 | 0.6565 | 1 | hit | 33.505 | 30721 | — |
| lb-flap-2 | partial | 0.60 | 0.6529 | 1 | hit | 32.583 | 30280 | — |
| node-leak-1 | partial | 0.60 | 0.6771 | 1 | hit | 18.325 | 14748 | — |
| node-leak-2 | exact | 1.00 | 0.7527 | 1 | hit | 31.409 | 28162 | — |
| dist-lock-1 | partial | 0.40 | 0.7216 | 1 | hit | 29.46 | 28322 | — |
| dist-lock-2 | exact | 1.00 | 0.69 | 1 | hit | 30.688 | 27920 | — |
