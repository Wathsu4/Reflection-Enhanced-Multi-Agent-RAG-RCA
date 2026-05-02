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

- `eval/incidents.jsonl` — 15 hand-authored scenarios:
  - 12 in-domain (two per seeded incident type — to test paraphrase
    robustness)
  - 3 out-of-distribution (DNS, rate limit, feature flag) — to test
    that the system gracefully says "no close match" rather than
    hallucinating one

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

A single run of the eval is necessarily noisy (one Gemini sample per
scenario). Running twice over the same scenarios — the default — gives
us a *reproducible direction of drift*, which is what the thesis claim
requires.

## Caveats

- Both scripts call Gemini end-to-end and so are subject to free-tier
  rate limits (~15 RPM). 12 in-domain scenarios × 4 sub-agents × 2 runs
  = 96 calls; budget ~10 minutes of wall time on a healthy connection.
- `evaluate.py` uses the production knowledge base by default. Run
  `evaluate_memory_evolution.py` first if you want a clean baseline,
  or use `scripts/reset_memory.py` directly.
- LLM-as-judge accuracy floors out around 80-90% even for human-perfect
  hypotheses; treat its absolute numbers as a sanity check on the
  keyword score, not as ground truth.
