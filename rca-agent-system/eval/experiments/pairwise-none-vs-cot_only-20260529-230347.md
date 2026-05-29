# Pairwise LLM-judge (bias-mitigated) — E4.2

**A = `none`** vs **B = `cot_only`** · 12 scenarios scored (3 errored)

6 votes/scenario (3 A/B + 3 B/A), explicit ignore-position-and-length instruction, reference-based.

- **A (none) wins:** 11 (92%)
- **B (cot_only) wins:** 0 (0%)
- **Ties:** 1 (8%)
- **Order-inconsistent** (A/B vs B/A majority disagreed): 1/12 — lower is less position bias

| id | winner | votes (a/b/tie) | order-consistent | error |
|---|---|---|---|---|
| redis-1 | none | 6/0/0 | yes |  |
| redis-2 | none | 6/0/0 | yes |  |
| jvm-oom-1 | — | 0/0/0 | yes | ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}} |
| jvm-oom-2 | — | 0/0/0 | yes | ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}} |
| deadlock-1 | none | 6/0/0 | yes |  |
| deadlock-2 | none | 6/0/0 | yes |  |
| upstream-1 | — | 0/0/0 | yes | ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}} |
| upstream-2 | none | 6/0/0 | yes |  |
| tls-1 | none | 6/0/0 | yes |  |
| tls-2 | none | 6/0/0 | yes |  |
| disk-1 | none | 6/0/0 | yes |  |
| disk-2 | none | 6/0/0 | yes |  |
| ood-dns | none | 4/2/0 | yes |  |
| ood-rate-limit | tie | 3/3/0 | NO |  |
| ood-feature-flag | none | 6/0/0 | yes |  |
