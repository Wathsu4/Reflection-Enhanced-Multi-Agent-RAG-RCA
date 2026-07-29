# Evaluation

Two evaluation scripts back the thesis numerical claims. Both depend on
a working agent service (env vars set, knowledge base seeded).

## Quick start

From `rca-agent-system/`:

```bash
# 1. Pipeline accuracy + latency on the curated dataset.
uv run python scripts/evaluate.py

# Same plus an LLM-as-judge column. Slower (3 Gemini calls per
# scenario), costs quota; useful for the thesis report.
uv run python scripts/evaluate.py --llm-judge

# Smoke test on the first 3 scenarios:
uv run python scripts/evaluate.py --limit 3

# 2. Memory-evolution: shows reflection-driven score drift over runs.
uv run python scripts/evaluate_memory_evolution.py
```

Outputs land under `eval/`:

- `results-{timestamp}.json` — full per-scenario record
- `results-{timestamp}.md` — thesis-ready summary table
- `memory-evolution-{timestamp}.md` — per-incident score drift table

## Dataset

- `eval/incidents.jsonl` — 15 hand-authored scenarios, the canonical
  demo-ready dataset, matched against the original 6-incident seed set:
  - 12 in-domain (two per seeded incident type — to test paraphrase
    robustness)
  - 3 out-of-distribution (DNS, rate limit, feature flag) — to test
    that the system gracefully says "no close match" rather than
    hallucinating one
- `eval/incidents_tier0_validation.jsonl` — 31 scenarios: those same 15
  plus 2 paraphrase-style scenarios per each of the 8 incidents Tier 0
  Phase 5 added (`seed/incidents/`, now 14 total). Use `--dataset
  eval/incidents_tier0_validation.jsonl` when you want to evaluate
  against the full, larger knowledge base rather than the original 6.

Each row has:

```json
{
  "id": "redis-1",
  "log_chunk": "...",
  "ground_truth_root_cause": "...",
  "ground_truth_keywords": ["redis", "..."],
  "expected_incident_id": "redis-conn-refused-001"
}
```

`expected_incident_id` is `null` for OOD scenarios.

## Scoring

Two metrics, composable on the same run:

1. **Keyword overlap** (default, deterministic). Fraction of curated
   keywords present in the extracted "Root cause" line. Bucketed into
   `exact` (≥ 0.66), `partial` (≥ 0.33), `miss` (< 0.33). Cheap and
   reproducible across runs but can't reward correct paraphrases.

2. **LLM-as-judge** (opt-in via `--llm-judge`). A separate Gemini call
   per hypothesis returns `yes` / `partial` / `no` against the ground
   truth. Single-shot judges are noisy, so each verdict is the
   majority vote across 3 calls. Slower and uses Gemini quota.

Side metrics computed from each run:

- `top_retrieval_similarity` — cosine similarity of the top hit (per
  Phase 6's contract).
- `expected_incident_retrieval_recall` — fraction of in-domain
  scenarios where the expected incident appeared in the retrieval
  output. (OOD scenarios are excluded from this denominator.)
- `mean_latency_s` / `p95_latency_s` — measured locally; dominated by
  Gemini RTT (~30-60s per pipeline run on the free tier).

## Memory-evolution evaluation

`evaluate_memory_evolution.py` is the headline experiment for the
project's novelty claim. It:

1. Wipes ChromaDB and reseeds it (so all `success_score` values start
   at 1.0).
2. Snapshots the score per incident.
3. Runs the in-domain subset of `incidents.jsonl` through the full
   pipeline, twice by default.
4. Snapshots scores again.
5. Renders a per-incident `baseline → after run 1 → after run 2`
   table.

Expected pattern: incidents that the reasoning agent correctly leans
on get boosted (final score > 1.0); incidents retrieved but judged
irrelevant get demoted (final score < 1.0). The drift summary at the
bottom of the report counts each.

A single run of the eval is necessarily noisy: each scenario is still
one draw through the pipeline, even though (as of Tier 0 Phase 4) the
reflection step itself internally averages `settings.reflection_ensemble_size`
(default 3) independent Gemini samples rather than trusting one. Running
the eval twice over the same scenarios — the default — gives us a
*reproducible direction of drift* across pipeline runs, which is what
the thesis claim requires; ensembling reduces noise *within* a single
run's reflection call, not across-run scenario variation.

## Caveats

- Both scripts call Gemini end-to-end and so are subject to free-tier
  rate limits (~15 RPM). 12 in-domain scenarios × 4 sub-agents × 2 runs
  = 96 calls; budget ~10 minutes of wall time on a healthy connection.
  Tier 0's reflection ensembling adds roughly 50% more tokens (not the
  naively-expected 3x — see `How-To-Improve/TIER0_PLAN.md` §9) on the
  reflection stage specifically; it does not change wall-clock latency
  materially since the samples run concurrently.
- `evaluate.py` uses the production knowledge base by default. Run
  `evaluate_memory_evolution.py` first if you want a clean baseline,
  or use `scripts/reset_memory.py` directly. **After pulling a change
  that touches `rca_system/memory/chroma_store.py`'s incident schema
  (e.g. Tier 0 Phase 2's `alpha`/`beta` pseudo-count fields) or
  `seed/incidents/` (e.g. Tier 0 Phase 5's KB expansion), run `just
  reset-demo` once** — old on-disk records don't retroactively gain new
  metadata fields or new incidents.
- LLM-as-judge accuracy floors out around 80-90% even for human-perfect
  hypotheses; treat its absolute numbers as a sanity check on the
  keyword score, not as ground truth.
