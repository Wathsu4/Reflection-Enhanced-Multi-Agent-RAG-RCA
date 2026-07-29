# RCA pipeline evaluation

- Variant (ablation): **reflection_off**
- Scenarios: **31** (28 in-domain, 3 OOD)
- Mean latency: **16.654s** (p95 ≈ 20.315s)
- Mean Gemini tokens / scenario: **12746.1**
- Mean top retrieval similarity: **0.651**
- Expected-incident retrieval recall (in-domain only): **1.0**
- Retrieval IR (in-domain, n=28, k=5): Recall@k=**1.0**, MRR=**0.982**, nDCG@k=**0.987**
- Keyword verdicts: exact=21, partial=8, miss=2 (exact-or-partial = **0.935**)

## Per-stage breakdown (mean across scenarios)

| stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent | 4.57 | 6122.484 |
| reasoning_agent | 6.77 | 3722.581 |
| retrieval_agent | 5.314 | 2901.0 |

## Per-scenario

| id | verdict | kw score | top sim | rank | expected hit | latency (s) | tokens | judge |
|---|---|---|---|---|---|---|---|---|
| redis-1 | exact | 1.00 | 0.7604 | 1 | hit | 16.527 | 12719 | — |
| redis-2 | partial | 0.50 | 0.5903 | 1 | hit | 17.77 | 13628 | — |
| jvm-oom-1 | exact | 0.80 | 0.8218 | 1 | hit | 17.246 | 13057 | — |
| jvm-oom-2 | exact | 1.00 | 0.6917 | 1 | hit | 15.383 | 12579 | — |
| deadlock-1 | partial | 0.60 | 0.6677 | 1 | hit | 16.624 | 12867 | — |
| deadlock-2 | partial | 0.50 | 0.6299 | 1 | hit | 16.243 | 12916 | — |
| upstream-1 | exact | 1.00 | 0.8055 | 1 | hit | 18.228 | 12768 | — |
| upstream-2 | exact | 0.80 | 0.3389 | 2 | hit | 17.248 | 12822 | — |
| tls-1 | exact | 0.80 | 0.725 | 1 | hit | 15.071 | 12262 | — |
| tls-2 | exact | 0.75 | 0.6527 | 1 | hit | 16.633 | 12985 | — |
| disk-1 | partial | 0.50 | 0.7834 | 1 | hit | 14.698 | 12390 | — |
| disk-2 | exact | 0.67 | 0.5625 | 1 | hit | 16.309 | 12111 | — |
| ood-dns | exact | 1.00 | 0.4059 | — | OOD | 19.464 | 12617 | — |
| ood-rate-limit | exact | 1.00 | 0.4197 | — | OOD | 16.835 | 12298 | — |
| ood-feature-flag | exact | 1.00 | 0.301 | — | OOD | 15.474 | 12311 | — |
| k8s-oom-1 | exact | 0.80 | 0.5595 | 1 | hit | 21.592 | 14623 | — |
| k8s-oom-2 | partial | 0.40 | 0.7228 | 1 | hit | 17.715 | 13460 | — |
| kafka-lag-1 | partial | 0.60 | 0.797 | 1 | hit | 15.207 | 12750 | — |
| kafka-lag-2 | exact | 0.80 | 0.7041 | 1 | hit | 19.216 | 13604 | — |
| db-pool-1 | exact | 0.80 | 0.6733 | 1 | hit | 16.142 | 12862 | — |
| db-pool-2 | miss | 0.00 | 0.661 | 1 | hit | 15.785 | 10318 | — |
| api-key-1 | partial | 0.60 | 0.7456 | 1 | hit | 18.49 | 13207 | — |
| api-key-2 | exact | 0.80 | 0.8279 | 1 | hit | 15.414 | 12910 | — |
| cdn-stale-1 | exact | 1.00 | 0.7577 | 1 | hit | 13.903 | 12765 | — |
| cdn-stale-2 | exact | 0.80 | 0.504 | 1 | hit | 17.722 | 13475 | — |
| lb-flap-1 | exact | 0.80 | 0.6852 | 1 | hit | 16.858 | 13336 | — |
| lb-flap-2 | exact | 0.80 | 0.6736 | 1 | hit | 17.041 | 13315 | — |
| node-leak-1 | exact | 0.80 | 0.574 | 1 | hit | 16.574 | 13048 | — |
| node-leak-2 | exact | 0.80 | 0.7701 | 1 | hit | 16.049 | 12942 | — |
| dist-lock-1 | partial | 0.40 | 0.6685 | 1 | hit | 15.053 | 12614 | — |
| dist-lock-2 | miss | 0.00 | 0.69 | 1 | hit | 13.751 | 9569 | — |
