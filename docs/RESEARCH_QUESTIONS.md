# Research-question coverage

How each of the proposal's RQs / ROs is realised in the implementation,
with concrete file pointers. Use this as the lookup when writing the
thesis defence chapter.

## RQ1 / RO1 — Reflective feedback for retrieval evaluation

**Claim.** A separate "reflection" agent can post-hoc evaluate which
retrieved past incidents actually informed the diagnosis and produce
a numerical signal for that judgement.

**Where it lives:**

- `rca-agent-system/rca_system/agents/reflection_agent.py` — the
  reflection sub-agent itself. Reads the original log chunk plus the
  retrieval and reasoning outputs from `session.state`, then calls
  `ensemble_reflect` (Tier 0 Phase 4) and echoes its result.
- `rca-agent-system/rca_system/tools/reflection_ensemble.py` — issues
  `settings.reflection_ensemble_size` (default 3) independent, concurrent
  Gemini judgments of the same retrieval/reasoning output
  (`asyncio.gather`), gates each individually, and aggregates (mean
  per-incident delta, majority-vote quality) before returning — the
  mechanism that turns one noisy judgment call into a signal with real
  statistical grounding.
- `rca-agent-system/rca_system/tools/record_reflection.py` — clamps
  deltas to `[-0.2, +0.2]` and deterministically **gates** them (Tier 0
  Phase 1): a positive delta survives only if the incident was actually
  cited as used by the reasoning stage; negative deltas are capped in
  count per call; exact-zero deltas are always dropped. Its gating
  logic is reused by `reflection_ensemble.py` per-sample. Has its own
  unit tests asserting the clamp boundary, the gating rules, and
  tolerating malformed inputs.
- `rca-agent-system/eval/incidents.jsonl` (canonical) and
  `eval/incidents_tier0_validation.jsonl` (31-scenario, 14-incident
  superset) — the datasets against which this loop is measured.
- `rca-agent-system/scripts/evaluate.py` — produces accuracy and
  latency metrics for the full pipeline, plus (Tier 0) the
  `reflection_positive_dropped_count` / `reflection_negative_dropped_count`
  / `reflection_ensemble_agreement` diagnostics that make the gate and
  the ensemble's internal consistency directly observable per scenario.

**Evidence from a run:** an early, un-calibrated smoke test showed
`redis-conn-refused-001` boosted by +0.2 and four irrelevant incidents
demoted by -0.2 in a single pipeline run — exactly the kind of
systematic, high-volume negative pile-on that Tier 0's gating (Phase 1)
and pseudo-count damping (Phase 2) were built to stop (see
`How-To-Improve/TIER0_PLAN.md` §1 for the mechanism that produced it and
§4–§7 for the fix). After Tier 0, a full validation run against the
14-incident KB (`eval/memory-evolution-20260728-224856.md`) showed 12 of
14 incidents boosted and **zero** demoted across 28 scenarios — the
signal is now systematically conservative about penalising incidents,
not systematically eager to.

## RQ2 / RO3 — Multi-agent architecture for retrieval / reflection / memory

**Claim.** Specialising agents to retrieval, reasoning, reflection, and
memory-update produces a clearer reasoning trace than a single
generalist agent and makes the pipeline auditable.

**Where it lives:**

- `rca-agent-system/rca_system/agent.py` — the top-level
  `SequentialAgent` orchestrator that wires the four sub-agents in
  pipeline order. `output_key` declarations on each child propagate
  state via `session.state`.
- `rca-agent-system/rca_system/agents/{retrieval,reasoning,reflection,memory_update}_agent.py`
  — one file per specialisation.
- `rca-agent-system/tests/test_pipeline.py` — composition tests
  asserting the sub-agent order, output-key contracts, and that each
  agent's instruction only references upstream state keys.
- `frontend/src/components/agents/AgentTimeline.tsx` — UI rendering of
  the per-agent steps that makes the architecture visible to the
  operator.

## RQ3 / RO4 — Dynamic memory updates over time

**Claim.** Per-incident `success_score`s adjusted by the reflection
agent re-rank retrieval results so the system improves as it sees more
incidents — without retraining anything.

**Where it lives:**

- `rca-agent-system/rca_system/memory/chroma_store.py` —
  `IncidentMemory.update_score(incident_id, delta)` converts the delta
  to a pseudo-count and folds it into the incident's `alpha`/`beta`
  prior (Tier 0 Phase 2); `success_score = 2*alpha/(alpha+beta)` is
  bounded to `(0.0, 2.0)` by construction and damps asymptotically —
  no single run's reflection can swing the score as far as it could
  under a plain linear-delta accumulator. `mark_retrieved` tracks usage.
- `rca-agent-system/rca_system/tools/retrieve_incidents.py` — the
  retrieval tool re-ranks with `similarity * success_score +
  exploration_bonus` after pulling the raw top-k (Tier 0 Phase 3): a
  small, decaying anti-starvation term so a demoted-but-rarely-retrieved
  incident always gets some chance to resurface, instead of the ranking
  formula alone being able to bury it permanently.
- `rca-agent-system/rca_system/tools/update_memory.py` — the
  `apply_reflection_to_memory` tool that the memory-update agent
  invokes; the only post-seed write path to `success_score`.
- `rca-agent-system/scripts/evaluate_memory_evolution.py` — generates
  the per-incident "baseline → after run 1 → after run 2" table.
  This is the headline experiment for the novelty claim.

**Evidence from a run (Tier 0 acceptance checkpoint,
`eval/memory-evolution-20260728-224856.md`, 14-incident KB, 28
in-domain scenarios, single pass):** every incident's `success_score`
moved from the 1.000 seed baseline to somewhere in `[1.000, 1.333]` —
12 boosted, 2 unchanged, 0 demoted, none anywhere near the `0.0`/`2.0`
clamp. On the full 7-variant ablation matrix over the same KB, the full
system (`none`) reached retrieval MRR 0.982 / nDCG@5 0.987, within
0.02 of the `memory_frozen` (static-memory) ablation's 1.0/1.0 — down
from an 0.208/0.156 gap on the original 6-incident KB before Tier 0.
Closing that gap (dynamic memory no longer *costing* retrieval quality
relative to not updating it at all) is the concrete, measured version
of "the system improves as it sees more incidents, without retraining
anything." See `How-To-Improve/TIER0_PLAN.md` §10 for the full
ablation table and the acceptance-bar reasoning.

## RQ4 / RO5 — Effectiveness vs manual investigation

**Claim.** A two-stage architecture (cheap classifier gating an
expensive multi-agent pipeline) bounds compute proportional to actual
incident rate rather than total log volume.

**Where it lives:**

- `classifier-service/app/classifier.py` — fine-tuned ModernBERT used
  as the cheap gate. Per-chunk inference is sub-50ms on Apple MPS;
  see `inference_ms` in the classify response.
- `frontend/src/lib/hooks/useInvestigationsQueue.ts` — only enqueues
  an RCA when the classifier returns `should_invoke_rca: true`.
  Sequential queue prevents parallel Gemini calls (also see Phase 9
  monitoring page wire-up).
- `rca-agent-system/scripts/evaluate.py` — reports `mean_latency_s`
  and `p95_latency_s` per pipeline run. Compare against the
  classifier's millisecond-scale latency for the gating ratio claim.
- Demo: `docs/DEMO.md` Act 3 — the live monitoring view illustrates
  this gating in real time.

## RO2 — Closed feedback loop

**Claim.** Retrieval → reasoning → reflection → memory mutation forms a
closed loop, where today's reflection biases tomorrow's retrieval.

**Where it lives:**

- The state-key chain documented in `rca-agent-system/rca_system/agent.py`
  (file header):

  `retrieval_output → reasoning_output → reflection_output → final_output → re-ranked retrieval_output for the next run`

- `tests/test_pipeline.py::test_*_references_only_upstream_state_keys` —
  asserts each agent only consumes upstream state keys, so the loop
  is correctly directed.
- `evaluate_memory_evolution.py` — second-run scores measurably
  differ from the first-run scores, demonstrating the loop closes.

## How to reproduce the numbers in the thesis

```bash
# Reset to seed state.
just reset-demo
# Run the pipeline accuracy + latency eval (writes a markdown report
# under rca-agent-system/eval/).
just eval --llm-judge
# Run the headline memory-evolution experiment.
just eval-memory
```

The two markdown reports in `rca-agent-system/eval/results-*.md` and
`memory-evolution-*.md` are the source for the thesis evaluation
chapter tables. The JSON sibling of the pipeline-accuracy report
contains the full per-scenario record (events, retrieval payloads,
extracted root cause) for any case-study commentary you want to drop
into the appendix.
