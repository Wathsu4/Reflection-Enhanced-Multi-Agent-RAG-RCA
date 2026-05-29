# Ablation & baseline matrix

Day-2 of the evaluation plan (PLAN.md §7). One run of all 15 scenarios per variant, each in an isolated freshly-seeded ChromaDB sandbox, with `--retries 3` on transient Gemini errors. Generated 2026-05-29.

> **Methodology note.** A first pass was discarded: a Gemini 503 *high-demand* spike during that ~16 min window caused 7-10 of 15 scenarios to error on the heavier 4-agent variants, artificially depressing them. We added scenario-level retry-with-backoff and re-ran; every variant below completed with 0 transient errors (1 residual on no_rag).

## Headline table

| Variant | Keyword acc (E+P) | exact/partial/miss | Retrieval recall | Recall@5 | MRR | nDCG@5 | Mean latency (s) | Mean tokens |
|---|---|---|---|---|---|---|---|---|
| Full system (none) | 0.933 | 12/2/1 | 1.0 | 1.0 | 0.836 | 0.876 | 28.263 | 21154.9 |
| Reflection OFF (E1.1) | 0.867 | 8/5/2 | 1.0 | 1.0 | 1.0 | 1.0 | 22.073 | 11311.5 |
| Memory FROZEN (E1.2) | 1.0 | 11/4/0 | 1.0 | 1.0 | 1.0 | 1.0 | 29.558 | 21422.9 |
| No-RAG (E1.4) | 0.933 | 10/4/1 | 0.0 | — | — | — | 9.858 | 4403.9 |
| CoT-only baseline (E2.2) | 1.0 | 10/5/0 | 0.0 | — | — | — | 9.753 | 4407.9 |
| Retrieval-only baseline (E2.1) | 0.133 | 1/1/13 | 1.0 | 1.0 | 1.0 | 1.0 | 0.057 | — |

## Per-stage cost (mean, full system `none`)

| Stage | latency (s) | tokens |
|---|---|---|
| memory_update_agent | 8.384 | 7864.4 |
| reasoning_agent | 7.259 | 3283.4 |
| reflection_agent | 6.927 | 7373.6 |
| retrieval_agent | 5.693 | 2633.533 |
