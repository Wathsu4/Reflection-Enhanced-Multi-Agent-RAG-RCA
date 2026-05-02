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
  `record_reflection` with per-incident deltas in `[-0.2, +0.2]`.
- `rca-agent-system/rca_system/tools/record_reflection.py` — clamps
  and structures the reflection's verdict. Has its own unit tests
  asserting the clamp boundary and tolerating malformed inputs.
- `rca-agent-system/eval/incidents.jsonl` — the dataset against which
  this loop is measured.
- `rca-agent-system/scripts/evaluate.py` — produces accuracy and
  latency metrics for the full pipeline.

**Evidence from a run:** Phase 7's smoke test showed
`redis-conn-refused-001` boosted by +0.2 and four irrelevant incidents
demoted by -0.2 in a single pipeline run.

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
  `IncidentMemory.update_score(incident_id, delta)` clamps to
  `[0.0, 2.0]`. `mark_retrieved` tracks usage.
- `rca-agent-system/rca_system/tools/retrieve_incidents.py` — the
  retrieval tool re-ranks with `similarity * success_score` after
  pulling the raw top-k.
- `rca-agent-system/rca_system/tools/update_memory.py` — the
  `apply_reflection_to_memory` tool that the memory-update agent
  invokes; the only post-seed write path to `success_score`.
- `rca-agent-system/scripts/evaluate_memory_evolution.py` — generates
  the per-incident "baseline → after run 1 → after run 2" table.
  This is the headline experiment for the novelty claim.

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
