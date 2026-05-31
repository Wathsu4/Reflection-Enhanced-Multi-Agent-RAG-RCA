# Pairwise LLM-judge (bias-mitigated) — E4.2

**A = `none`** vs **B = `react`** · 15 scenarios scored (0 errored)

6 votes/scenario (3 A/B + 3 B/A), explicit ignore-position-and-length instruction, reference-based.

- **A (none) wins:** 8 (53%)
- **B (react) wins:** 5 (33%)
- **Ties:** 2 (13%)
- **Order-inconsistent** (A/B vs B/A majority disagreed): 4/15 — lower is less position bias

| id | winner | votes (a/b/tie) | order-consistent | error |
|---|---|---|---|---|
| redis-1 | none | 6/0/0 | yes |  |
| redis-2 | tie | 3/3/0 | NO |  |
| jvm-oom-1 | none | 4/2/0 | NO |  |
| jvm-oom-2 | react | 0/6/0 | yes |  |
| deadlock-1 | none | 6/0/0 | yes |  |
| deadlock-2 | react | 1/5/0 | yes |  |
| upstream-1 | react | 0/6/0 | yes |  |
| upstream-2 | none | 6/0/0 | yes |  |
| tls-1 | none | 6/0/0 | yes |  |
| tls-2 | react | 0/6/0 | yes |  |
| disk-1 | none | 6/0/0 | yes |  |
| disk-2 | none | 6/0/0 | yes |  |
| ood-dns | tie | 3/3/0 | NO |  |
| ood-rate-limit | react | 2/4/0 | NO |  |
| ood-feature-flag | none | 5/1/0 | yes |  |
