# Tier 0 Implementation Plan — Fix the Reflection/Memory Mechanism

Status: **ready to execute** (authored via actor-critique review, see §3 for the review log)
Scope: `rca-agent-system/` only. One feature branch, one pull request, six implementation phases.
Companion doc: this plan operationalizes items 0.1–0.5 from the improvement-list conversation
(the reflection-driven memory re-ranking is the thesis's core novelty claim per
`thesis/Chapter_2_Literature_Review.md` §2.9.2 gap G3/G4, and `docs/RESEARCH_QUESTIONS.md` RQ3/RO2).

---

## 1. Why this tier exists (evidence, not opinion)

From `rca-agent-system/eval/experiments/SUMMARY-ablation-matrix.md` (reproduced 2026-07-27):

| Variant | Keyword acc | Retrieval MRR | nDCG@5 | Mean latency |
|---|---|---|---|---|
| **Full system (`none`)** | 0.933 | **0.836** | **0.876** | 28.3s |
| **Memory FROZEN** (reflection runs, scores never persisted) | **1.0** | **1.0** | **1.0** | 29.6s |

Turning the score-persistence *off* currently beats leaving it *on*. The memory-evolution
experiment explains the mechanism: with 6 seed incidents and `k=5` retrieval, ~83% of the
catalog is touched by every single query. `reflection_agent`'s instruction says "0.0 if
retrieved but neutral," but Gemini does not reliably default to neutral — in practice most
retrieved-but-uncited incidents get a small negative nudge. Since each incident gets far more
"uncited" exposures than "genuinely used" ones, this is a textbook **Matthew effect**
(rich-get-richer / poor-get-poorer, well documented in the bandit/recommender-systems
literature) and it fully explains the observed pattern: 5 of 6 incidents got demoted (one hit
the floor of 0.0) and only the most lexically distinctive incident (Redis) trended up.

This is fixable. It is not evidence that the underlying idea (reflection-biased retrieval) is
wrong — it's evidence that the *current calibration* of the reflection→score pipeline is
mis-tuned. Tier 0 fixes the calibration and proves it with the same ablation harness that
found the problem.

---

## 2. Execution protocol — read this before starting Phase 0

**Branching & PR:** Create exactly one branch (e.g. `tier0-reflection-memory-fix`). Commit once
per phase (a clean, test-passing commit is the rollback unit — `git revert` a phase if it turns
out to be wrong). **Do not open a pull request until Phase 6 is completely finished.** All six
phases land in a single PR against `main`/`master`.

**The actor-critique loop (run this for every phase, no exceptions):**

1. **ACTOR** — implement exactly what the phase section specifies. If you must deviate, write
   down why in the phase's checklist before continuing.
2. **ACTOR** — run the phase's new/updated tests, then the full test suite for the affected
   sub-project (`cd rca-agent-system && uv run pytest -q`).
3. **CRITIC** — re-read your own diff adversarially against that phase's "Critique checklist."
   Do not skim it. Assume there is a bug and go looking for it.
4. **CRITIC** — construct at least one adversarial case not already in the plan's test list
   (empty retrieval, all-negative deltas, unknown incident id, k larger than the KB, a
   reflection call with zero retrieved incidents, etc.) and verify it's handled.
5. If CRITIC finds *anything*, go back to step 1. Repeat until CRITIC has nothing left to flag.
6. Only then: commit, check off the phase's boxes in this file, move to the next phase.

Do not batch phases together "to save time." The point of phase boundaries is that each one is
independently revertable and independently defensible in front of an examiner.

**Cost/time awareness:** Phases 0–3 are pure unit-testable Python (no Gemini key required for
the test suite itself). Phases 1's prompt-compliance check, Phase 4, and Phase 5 require live
Gemini calls and will consume real API quota — use `--limit 2` or `--limit 3` smoke runs while
iterating, and reserve full-matrix runs for the checkpoint at the end of each phase. Phase 5
alone (7 ablation variants × ~18 scenarios) is roughly 30–60+ minutes of live calls; do not run
it repeatedly out of habit.

---

## 3. Plan authoring log (actor-critique applied to this document)

This plan was drafted, then critiqued, then revised, across two rounds before being accepted.
Recorded here so the rationale for non-obvious decisions isn't lost.

**Round 1 findings → fixes applied:**
- *"Omit vs. zero" is unenforceable by prompt alone.* Gemini cannot be trusted to reliably omit
  a JSON key just because the instruction says so. Fix: the gating logic moved from "hope the
  agent omits it" to a **deterministic, code-enforced gate** inside `record_reflection` — see
  Phase 1.
- *No way to tell "genuinely irrelevant" from "merely not the top pick."* Positive deltas can be
  checked objectively (was the id in `used_incident_ids`?); negative deltas cannot, since
  "misleading" is a judgment call. Fix: split the two — positive deltas are gated
  deterministically, negative deltas are capped in *count* (at most
  `max_negative_delta_fraction` of the retrieved set) rather than trusted unconditionally.
- *Phase 5 as originally scoped (50–200 new incidents) would blow up this PR.* That's a
  separate, larger effort. Fix: descoped to a bounded 2–3× expansion (6 → ~12–18 incidents),
  enough to meaningfully drop the k/N exposure ratio, with full-scale stress testing explicitly
  deferred (§9).
- *Schema change breaks existing on-disk ChromaDB state silently.* Fix: treated as a documented
  breaking change requiring `just reset-demo` post-upgrade (rejected building migration/backfill
  logic for a research prototype's fully-regenerable vector index — not worth the complexity).

**Round 2 findings → fixes applied:**
- *No incremental checkpoint between phases* meant a regression introduced in Phase 2 might not
  surface until Phase 5's full matrix run, days later. Fix: each phase gets a cheap
  `none` vs `memory_frozen` (or scenario-limited) checkpoint, not just a final one.
- *Ensembling (0.4) as originally imagined risked restructuring the ADK `SequentialAgent` graph*
  (e.g. via a `LoopAgent`), which would invalidate `tests/test_pipeline.py`'s composition
  assertions and the state-key contract documented in `rca_system/agent.py`. Fix: Phase 4's
  primary design keeps the 4-agent flat structure intact and ensembles *inside* the single
  `reflection_agent` slot, mirroring the 3-sample majority-vote pattern `scripts/evaluate.py
  --llm-judge` already uses elsewhere in this codebase. The graph-restructuring approach is kept
  as a documented fallback only.
- *`IncidentMemory.update_score`'s existing single-call saturation test would silently start
  failing* once Phase 2 changes the internals from "add-then-clamp" to "bounded pseudo-count."
  This is an intentional behavior change (no single call should swing a score straight to an
  extreme), not a bug — but it must be called out and the test rewritten, not just left broken
  or deleted. Fixed explicitly in Phase 2's checklist.
- *Exploration bonus could reintroduce nondeterminism into a currently-deterministic-order test*
  (`test_dynamic_reranking_boosts_high_score_hits`). Fix: bonus formula depends only on
  `usage_count`, which is identical (zero) for both records in that test, so tie-breaking by
  score is preserved — made explicit as a required non-regression check in Phase 3.

**Round 3:** no further blocking issues found. Plan accepted.

---

## 4. Design spec — single source of truth for formulas & config

New settings in `rca_system/settings.py` (`Settings` class), all overridable via
`rca-agent-system/.env`:

| Setting | Default | Used by | Meaning |
|---|---|---|---|
| `max_negative_delta_fraction` | `0.4` | Phase 1 | At most this fraction of the *retrieved* set may receive a negative delta per reflection call. |
| `score_prior_strength` | `2.0` | Phase 2 | Initial `alpha`/`beta` pseudo-count prior (higher = more resistant to early swings). |
| `delta_to_pseudocount_scale` | `0.2` | Phase 2 | Divisor mapping a clamped delta to a pseudo-count (`0.2` ⇒ a max-magnitude delta = 1.0 pseudo-count). |
| `exploration_bonus_weight` | `0.1` | Phase 3 | Weight on the anti-starvation exploration term. |
| `reflection_ensemble_size` | `3` | Phase 4 | Number of parallel reflection samples to aggregate. Set to `1` to reproduce today's single-shot behavior for cheap iteration. |

**Phase 1 — delta gating (exact rule):**
- `record_reflection` gains two new required params: `used_incident_ids: list[str]` and
  `retrieved_incident_ids: list[str]` (both already available to `reflection_agent` via
  `{reasoning_output?}` and `{retrieval_output?}`).
- Any **positive** delta for an id not in `used_incident_ids` → dropped (not zeroed — removed
  from the returned dict entirely).
- **Negative** deltas: allowed up to `ceil(len(retrieved_incident_ids) * max_negative_delta_fraction)`
  entries. If more are proposed, keep the largest-magnitude ones up to that count; drop the rest.
- Entries with delta exactly `0.0` are dropped unconditionally (a "no-op" delta carries no
  information and should never reach `apply_reflection_to_memory`).
- Everything else (clamping to ±0.2, non-numeric handling, list-of-objects reshaping) keeps its
  current behavior from `record_reflection.py` — this phase only adds the gate, it doesn't
  remove existing robustness.

**Phase 2 — confidence-weighted score (exact formula):**
- `IncidentRecord` gains `alpha: float = score_prior_strength` and
  `beta: float = score_prior_strength`.
- Derived `success_score = 2 * alpha / (alpha + beta)` — at the default prior (2.0/2.0) this is
  exactly `1.0`, matching today's neutral starting value.
- `IncidentMemory.update_score(incident_id, delta)`: first re-clamp `delta` to `[-0.2, 0.2]`
  (defense-in-depth, independent of the tool-level clamp — preserves the existing
  "no single call can be catastrophic" property, just at the pseudo-count layer instead of the
  raw-score layer). Compute `pseudocount = abs(clamped_delta) / delta_to_pseudocount_scale`
  (max `1.0`). Add `pseudocount` to `alpha` if `delta > 0`, to `beta` if `delta < 0`. Recompute
  and persist `success_score`, `alpha`, `beta` together.
- `success_score` stays a stored metadata field (not computed lazily at read time), so
  `retrieve_incidents.py`'s ranking code needs **zero changes** — it keeps reading
  `metadata["success_score"]` exactly as today.
- Migration: this changes the metadata schema. **Decision: do not backfill.** Document in the PR
  and in `AGENTS.md`/`README.md` that `just reset-demo` (or a fresh `uv run python
  scripts/seed_knowledge_base.py` into a clean dir) must be run once after deploying Tier 0. This
  is consistent with how the project already treats memory as regenerable, disposable state.

**Phase 3 — exploration bonus (exact formula):**
- New ranking key in `retrieve_incidents.py`:
  `similarity * success_score + exploration_bonus_weight * sqrt(1 / (1 + usage_count))`
  (additive, not multiplicative — a `success_score` of exactly `0.0` still leaves the bonus term
  intact, which is the whole point: a starved incident can still resurface).
- At `usage_count=0` the bonus is `exploration_bonus_weight` (default `0.1`); it decays toward
  `0` as an incident accumulates retrievals. It never dominates a genuinely strong match
  (`similarity * success_score` ranges up to `2.0`; the bonus is capped at `0.1` by default).

**Phase 4 — ensembling (exact aggregation rule):**
- Preferred implementation: a custom aggregation layer invoked from within the single
  `reflection_agent` pipeline slot, issuing `reflection_ensemble_size` concurrent Gemini calls
  (via `asyncio.gather`, so wall-clock latency does not scale with the ensemble size — only
  token cost does) and aggregating before the one `record_reflection` call.
- Per-incident delta aggregation: **mean** across samples that proposed *any* delta for that id
  (post Phase-1 gating, per sample); an id proposed by zero samples gets no entry.
- `overall_quality` aggregation: majority vote across the 3 samples; ties broken toward the more
  conservative label (`low` > `medium` > `high` in a tie).
- Fallback (only if the primary approach proves infeasible against this ADK version): wrap
  `reflection_agent` in an ADK `LoopAgent` fixed at `reflection_ensemble_size` iterations plus a
  small deterministic aggregator sub-agent. This changes `root_agent`'s sub-agent shape and
  **requires** updating `tests/test_pipeline.py` and re-checking every place that assumes
  exactly 4 named sub-agents (`AGENTS.md` §6, `rca_system/ablations.py`'s clone logic). Prefer
  the primary approach; only fall back here with an explicit note in the PR description of why.

---

## 5. Phase 0 — Baseline, safety net, instrumentation

**Goal:** capture a trustworthy "before" snapshot and add the config surface later phases need,
with zero behavior change.

**Changes:**
- [x] Add the five settings from §4 to `rca_system/settings.py` with the defaults listed (adding
      them now, unused, keeps every later phase a smaller diff).
- [x] Re-run and archive a fresh baseline: `just reset-demo`, then
      `uv run python scripts/evaluate.py --ablation none` and
      `uv run python scripts/evaluate.py --ablation memory_frozen` (write outputs to
      `eval/experiments/`, they're timestamped automatically — do not overwrite the existing
      2026-05-29 matrix, it stays as historical record). Also run
      `uv run python scripts/evaluate_memory_evolution.py`.
- [x] Add optional, currently-unpopulated diagnostic fields to `ScenarioResult` in
      `scripts/evaluate.py`: `reflection_positive_dropped_count`,
      `reflection_negative_dropped_count`, `reflection_ensemble_agreement` (default `None`/`0`).
      These stay inert until Phases 1 and 4 populate them — added now so those phases' diffs are
      additive, not "add field + add test + wire it up" all at once.
- [x] No production code path changes behavior in this phase.

**Baseline results (recorded 2026-07-27):**
- `none` (full system): reused the same-day pre-existing run at
  `eval/results-20260727-222918.{json,md}` (generated before any Tier 0 code changes, on the same
  commit this branch was cut from — no need to re-spend quota reproducing it). Keyword accuracy
  (E+P) **1.0** (11 exact / 4 partial / 0 miss), retrieval **MRR 0.792**, **nDCG@5 0.844**, mean
  latency 23.88s. Memory-evolution (same reused artifact,
  `eval/memory-evolution-20260727-224016.md`): 5/6 incidents demoted after 2 runs, one
  (`db-deadlock-001`) hit the floor of `0.000`, only `redis-conn-refused-001` trended up (1.200) —
  matches the Matthew-effect narrative in §1 exactly.
- `memory_frozen`: freshly captured this session at
  `eval/experiments/results-memory_frozen-20260727-235419.{json,md}`. Keyword accuracy (E+P)
  **1.0** (10 exact / 5 partial / 0 miss), retrieval **MRR 1.0**, **nDCG@5 1.0**, mean latency
  22.08s.
- Gap being fixed by Tier 0: `none` vs `memory_frozen` MRR gap is **0.208** (0.792 vs 1.0) and
  nDCG@5 gap is **0.156** (0.844 vs 1.0). (§1's originally-quoted 0.836/0.876 for `none` came from
  a different sampling of the same non-deterministic pipeline — Gemini's retrieval-query wording
  varies run to run, so a few points of MRR/nDCG drift between two "clean" `none` runs is expected
  noise, not a regression. The underlying finding — freezing persistence beats leaving it on — is
  reproduced clearly either way.)

**Tests:** none new. Full existing suite (`uv run pytest -q`) must pass unchanged — this phase
*is* the regression baseline. Confirmed: **128 passed**, 0 failed, before and after this phase's
changes.

**Checkpoint:** N/A (this phase produces the checkpoint baseline for every later phase to diff
against).

**Critique checklist:**
- [x] Did any of the new settings accidentally get a default that changes existing behavior
      (e.g. if some code path already reads a same-named field)? Grep for each new setting name
      before adding it. — Grepped all five names across `rca-agent-system/` before adding; zero
      pre-existing references. Full suite still 128/128 after the change.
- [x] Does the freshly-captured baseline match (roughly) the numbers quoted in §1? If it's wildly
      different, find out why before proceeding — you may be measuring a different starting
      state (e.g. leftover drift from a prior manual session). — Keyword accuracy matches exactly
      (1.0 exact-or-partial for both `none` and `memory_frozen`, same as §1). MRR/nDCG for `none`
      (0.792/0.844 vs §1's 0.836/0.876) differ by ~0.03-0.04 — attributed to normal run-to-run
      retrieval-query wording noise (Gemini re-generates the search query every run), not a
      different starting state; `memory_frozen` reproduced §1's 1.0/1.0/1.0 exactly. Not wild —
      proceeding.
- [x] Confirm `eval/results-*.md` (the demo-ready location) is untouched — baseline captures
      must go through `--ablation` flags so they land in `eval/experiments/`, not `eval/`. —
      Clarification: `scripts/evaluate.py` routes `--ablation none` to `eval/` by design (it's the
      demo-ready "full system" report location; see its `amain()`: `if ablation == "none": out_dir
      = EVAL_DIR`) and every other ablation to `eval/experiments/`. That's existing, intentional,
      tested behavior (matches every prior `none` run already committed in `eval/`) — not a Tier 0
      change, and not something this phase alters. The `memory_frozen` baseline correctly landed
      in `eval/experiments/`. No unintended writes to `eval/results-*.md` occurred this session.

---

## 6. Phase 1 — Deterministic delta gating (fixes item 0.1)

**Goal:** stop the systematic negative-drift bias by making the "was this actually used"
question a code-enforced gate instead of a prompt-compliance hope.

**Changes:**
- [x] `rca_system/tools/record_reflection.py`: extend `record_reflection` signature to
      `(incident_score_deltas, overall_quality, rationale, used_incident_ids=None,
      retrieved_incident_ids=None)`. Implement the exact gating rule from §4. Keep both new
      params optional with safe defaults (`None` → treat as "gate nothing" / "cap nothing") so
      **direct unit tests of the old 3-arg call shape don't all need to change at once** — but
      note in the docstring that the pipeline always supplies both from here on.
- [x] `rca_system/agents/reflection_agent.py`: update the instruction to (a) explain the new
      tool params and instruct the agent to pass `used_incident_ids` from
      `{reasoning_output?}` and `retrieved_incident_ids` from the ids present in
      `{retrieval_output?}`, and (b) strengthen the neutral-scoring language (explicit "if in
      doubt, omit it" framing, and require the `rationale` to name any incident it assigns a
      negative delta to).
- [x] `scripts/evaluate.py`: populate the two new diagnostic counters added in Phase 0 from the
      gate's before/after counts (requires `record_reflection`, or a thin wrapper around it, to
      report what it dropped — return an extra `_debug` key is acceptable here since it's
      evaluation-only consumption; the production pipeline ignores it).

**Deviation (found and fixed, not in the original plan):** the naive `FunctionTool(func=record_reflection)`
registration broke the *live* pipeline outright — `google-adk==1.32.0` on Python 3.14 has a bug
(matches [google/adk-python#5364](https://github.com/google/adk-python/issues/5364)) where any
`Optional[list[str]]`/`list[str] | None` parameter forces the tool's *entire* schema through a
`pydantic.TypeAdapter(...).json_schema()` fallback that emits a snake_case `additional_properties`
key instead of the API's `additionalProperties`. `gemini-2.5-flash` 400s on the unrecognized field
("Unknown name \"additional_properties\" ... Cannot find field") — confirmed via a `--limit 3`
smoke run that failed 3/3 with that exact `ClientError` once `used_incident_ids`/
`retrieved_incident_ids` were added. The fallback is contagious: it also corrupted the
already-shipping `incident_score_deltas: dict[str, float]` parameter's schema, which had been
fine for months. Root-caused offline (no API calls) by diffing `FunctionTool()._get_declaration()`
output across signature variants — confirmed the trigger is specifically a default value that
fails ADK's `isinstance(default, annotation)` compatibility check (`None` is never an instance of
`list`), which is true for `Optional[...]`/`X | None` regardless of `typing.Optional` vs PEP 604
spelling (Python 3.14 unifies both under `types.UnionType`, so there is no "cleaner" spelling that
dodges it on this Python version). Fix: added `_RecordReflectionTool(FunctionTool)` in
`reflection_agent.py`, overriding `_get_declaration()` with a hand-built, bug-free schema
(`used_incident_ids`/`retrieved_incident_ids` as plain required `ARRAY` of `STRING`, matching what
the updated instruction already guarantees Gemini will supply); `record_reflection`'s real Python
signature — and thus every test above and the back-compat contract — is untouched. Added
`test_record_reflection_tool_schema_has_no_additional_properties_or_any_of` in
`tests/test_pipeline.py` as a regression pin. This is a required fix to make Phase 1 function at
all on this stack, not scope creep; noting it here per the plan's own "write down why" rule.

**Tests (`tests/test_record_reflection.py`):**
- [x] Positive delta for an id **not** in `used_incident_ids` → dropped.
- [x] Positive delta for an id **in** `used_incident_ids` → kept, value unchanged (post-clamp).
- [x] Negative deltas within the cap (`≤ ceil(N_retrieved * 0.4)`) → all kept.
- [x] Negative deltas exceeding the cap → only the largest-magnitude ones up to the cap survive;
      verify which ones are dropped, not just the count.
- [x] A delta of exactly `0.0` → dropped regardless of `used_incident_ids`.
- [x] `used_incident_ids=None` / `retrieved_incident_ids=None` (back-compat call shape) →
      behaves exactly like the pre-Phase-1 tool (no gating applied) — this is the explicit
      backward-compatibility contract, write a test that pins it.
- [x] Existing tests (`test_clamps_deltas_to_plus_minus_zero_point_two`,
      `test_skips_non_numeric_delta_values`, `test_accepts_list_of_objects_format`, etc.) must
      still pass — update their call sites to pass explicit `used_incident_ids`/
      `retrieved_incident_ids` only where the test's intent requires it; otherwise leave them
      relying on the `None` back-compat path. (None needed changes — all pass unmodified via the
      back-compat path.)
- Plus two adversarial cases found during the critique loop, not in the original list:
  `test_positive_gate_disabled_but_retrieved_universe_filter_still_applies` (the two gates are
  independent, not paired) and the ADK schema regression test noted above.

**Checkpoint (live Gemini, small) — results recorded 2026-07-28:**
- [x] Ran `uv run python scripts/evaluate.py --ablation none --limit 3` and read the raw
      `record_reflection` tool call/response pairs from `raw_events` in the JSON. Confirmed Gemini
      reliably supplies non-empty, accurate `used_incident_ids` (e.g. scenario `redis-2`: reasoning
      cited only `redis-conn-refused-001`, reflection proposed one matching positive delta plus
      *four* negative deltas for every other retrieved incident — the exact Matthew-effect pattern
      from §1 — and the gate correctly kept the 2 highest-magnitude negatives (`disk-full-log-001`,
      `upstream-timeout-payments-001`) and dropped the other 2
      (`tls-cert-expired-001`, `db-deadlock-001`), matching `_debug: {positive_dropped_count: 0,
      negative_dropped_count: 2}`). No prompt-compliance concern found; reasoning_agent's
      `used_incident_ids` emission is already reliable enough for the gate to do real work.
- [x] Ran the full 15-scenario dataset for both variants (fresh reset before each):
      **`none`**: keyword acc (E+P) **1.0** (11 exact/4 partial/0 miss), retrieval **MRR 1.0**,
      **nDCG@5 1.0**, mean latency 24.04s (`eval/results-20260728-065329.{json,md}`).
      **`memory_frozen`**: keyword acc (E+P) **1.0** (11 exact/4 partial/0 miss), retrieval
      **MRR 1.0**, **nDCG@5 1.0**, mean latency 25.22s
      (`eval/experiments/results-memory_frozen-20260728-065957.{json,md}`).
      **Gap vs Phase 0:** MRR gap closed from **0.208 → 0.0**, nDCG@5 gap closed from
      **0.156 → 0.0** — the two variants are now indistinguishable on this metric on the current
      6-incident KB. (Phase 5's expanded KB is the real stress test for whether this holds once
      k=5 no longer covers ~83% of the catalog; flagging here that Phase 1 alone already closes
      the gap at the *current* KB size, which is a strong but not yet fully generalized result.)

**Critique checklist:**
- [x] Does the gate correctly handle `retrieved_incident_ids` being **shorter** than
      `incident_score_deltas` (reflection hallucinated an id that wasn't even retrieved)? Decide
      and test explicitly: such an id should be dropped (it can't be verified against either
      list meaningfully) — write the test. — `test_id_not_in_retrieved_incident_ids_is_dropped`.
- [x] Does the fraction-based negative cap round sensibly at small N (e.g. `N_retrieved=1`:
      `ceil(1*0.4)=1`, so a single retrieved-and-irrelevant incident can still be penalized —
      confirm this is the intended behavior, not an off-by-one that zeroes out all negative
      signal when only 1–2 incidents are retrieved). — `test_negative_cap_rounds_up_for_small_retrieved_sets`
      confirms 1 negative delta survives at N=1; matches design intent.
- [x] Confirm `apply_reflection_to_memory` and `IncidentMemory.update_score` were **not**
      touched in this phase — Phase 1 only changes what makes it into the dict, not how the dict
      is applied. If you find yourself editing `update_memory.py`, stop — that's Phase 2's job. —
      `git diff --stat` confirms zero changes to either file.
- [x] Re-run the full `rca-agent-system` test suite, not just `test_record_reflection.py` —
      `test_pipeline.py` and `test_agent_loads.py` touch the reflection agent's instruction
      string; confirm nothing asserts on the old instruction text verbatim. — Full suite green
      (145 passed); grepped tests/ for old instruction substrings ("skeptical senior engineer",
      "hand-waving", "neutral evidence") — no verbatim-text assertions found anywhere.

---

## 7. Phase 2 — Confidence-weighted score accumulation (fixes item 0.2)

**Goal:** make the score a stable running signal (stickier with more evidence) instead of an
unbounded random walk, independent of Phase 1's acute fix.

**Changes:**
- [ ] `rca_system/memory/chroma_store.py`: add `alpha`/`beta` fields to `IncidentRecord`
      (defaults from `settings.score_prior_strength`). Rewrite `update_score` per the §4 formula.
      Keep the public signature `update_score(incident_id, delta)` unchanged — callers
      (`update_memory.py`) need no changes.
- [ ] `rca_system/tools/update_memory.py`: no logic changes expected (it already just calls
      `memory.update_score` and re-reads `success_score` before/after) — verify this is actually
      true once Phase 2 lands, don't assume it.
- [ ] Update `README.md` / `AGENTS.md` (§4 env var table, §6 tool description) and
      `docs/DEMO.md` to note the schema change and the required `just reset-demo` after
      upgrading.

**Tests — this phase *requires* rewriting, not just re-running:**
- [ ] `tests/test_update_memory.py::test_returns_old_new_delta_per_id` and
      `test_persists_new_score_to_memory`: recompute expected values from the new formula (not
      simple addition) — show your arithmetic in a test comment so a reviewer can check it by
      hand.
- [ ] `tests/test_update_memory.py::test_repeated_positive_deltas_clamp_at_2` /
      `test_repeated_negative_deltas_clamp_at_0`: these currently expect saturation in 2–3 calls
      at the old linear-add rate; recompute how many calls it now takes under the pseudo-count
      model and update the loop count and expected value accordingly. Do not just increase the
      loop count until the old assertion happens to pass again without understanding why —
      derive the expected `alpha`/`beta`/`success_score` explicitly.
- [ ] `tests/test_chroma_store.py::test_update_score_clamps_to_range`: this test currently
      expects **one call** with `delta=10.0` to saturate at `2.0`. Under Phase 2 this is no
      longer true by design (re-clamped to `0.2` → `1.0` pseudo-count → from the default prior
      `alpha=2,beta=2`, one call yields `alpha=3,beta=2` → `success_score=1.2`, *not* `2.0`).
      Rewrite this test to assert (a) a single extreme call moves the score by a bounded amount
      matching the formula, and (b) **repeated** extreme calls eventually saturate at the bound —
      add a new test for each. Do not delete the "eventually saturates" guarantee, it's load
      bearing for the "runaway reputation" defense described in `docs/DEFENSE_GUIDE.md`.
- [ ] New test: an incident seeded fresh (`alpha=beta=score_prior_strength`) has
      `success_score == 1.0` exactly — pins the "prior is neutral" invariant.
- [ ] New test: `test_seed_knowledge_base.py` and `test_reset_memory.py` still produce
      `success_score == 1.0` for every seeded record (should pass unchanged since
      `build_record()` doesn't set `alpha`/`beta` explicitly and the dataclass defaults handle
      it — verify this rather than assuming it).

**Checkpoint (live Gemini):**
- [ ] Run `evaluate_memory_evolution.py --runs 3` (bumped from 2, to see a longer trend) on the
      existing dataset. Compare against Phase 0/Phase 1 baselines: scores should move by visibly
      smaller increments per run and should not hit the `0.0`/`2.0` clamp within 3 runs unless an
      incident is being *very* consistently flagged as misleading. Record the per-incident table
      in the PR description.

**Critique checklist:**
- [ ] Confirm the re-clamp inside `update_score` uses the **same** bound constant as
      `record_reflection`'s `_DELTA_MIN`/`_DELTA_MAX` (import/share it — do not duplicate the
      literal `0.2` in two files where it can silently drift out of sync).
- [ ] Confirm `retrieve_incidents.py` was **not** touched in this phase (it should keep reading
      `metadata["success_score"]` unchanged — if you found yourself editing it, that's a sign
      the derived-field caching isn't working and needs to be fixed here, not deferred).
- [ ] Check the migration story is actually documented somewhere a future reader will see it
      (`AGENTS.md` env var table is the most likely place someone checks) — not just mentioned in
      a commit message.
- [ ] Does `mark_retrieved`'s `usage_count` interact with the new `alpha`/`beta` bookkeeping in
      any surprising way (e.g. double-counting)? They should remain fully independent counters —
      write a test that bumps `usage_count` via retrieval without touching `alpha`/`beta`, and
      vice versa.

---

## 8. Phase 3 — Exploration floor / anti-starvation (fixes item 0.3)

**Goal:** guarantee no incident can be permanently buried by the ranking formula.

**Changes:**
- [ ] `rca_system/tools/retrieve_incidents.py`: change the sort key per the §4 formula. Update
      the function's docstring (remember: **Gemini reads this docstring** to decide how to call
      the tool — review the wording change for clarity from the calling model's perspective, not
      only a human reader's).

**Tests (`tests/test_retrieve_incidents.py`):**
- [ ] New: an incident with `success_score=0.0` and `usage_count=0` ranks **above** a competing
      incident with a low-but-nonzero score and a high `usage_count`, when raw similarity is
      comparable — proves the starvation floor works.
- [ ] New: an incident with `success_score=0.0` does **not** outrank a genuinely strong match
      (high similarity, `success_score` near neutral) — proves the bonus doesn't overwhelm real
      signal. Pick concrete numbers and show the arithmetic in the test.
- [ ] Regression: `test_dynamic_reranking_boosts_high_score_hits` must still pass unmodified —
      both records in that test have `usage_count=0`, so the bonus term is identical for both and
      cancels out of the comparison; if this test needs to change, something is wrong with the
      formula's tie-breaking, not the test.
- [ ] New: bonus magnitude is bounded — verify at `usage_count=0` the bonus never exceeds
      `exploration_bonus_weight` (i.e. the formula can't blow up for any valid input).

**Checkpoint:**
- [ ] Small script or test simulating N=5 consecutive "neutral" retrievals of a
      zeroed-out incident (via direct `IncidentMemory` calls, no live Gemini needed) — confirm
      its rank among a fixed candidate set improves as `usage_count` climbs even while
      `success_score` stays at `0.0`. This is a pure-Python checkpoint, no API cost.

**Critique checklist:**
- [ ] Could the exploration bonus ever change the **order** of the top-1 result in a way that
      degrades `expected_incident_retrieval_recall`? Re-run `evaluate.py --ablation none --limit
      5` and confirm recall@1 for in-domain scenarios is unaffected — this is exactly the kind of
      side effect a well-intentioned bonus term can cause and it's cheap to check.
- [ ] Is `usage_count` reset anywhere unexpectedly (e.g. by `reset_memory.py`, which re-seeds
      from scratch) — confirm the exploration bonus behaves sanely immediately after a reset
      (every incident at `usage_count=0`, so the bonus is uniform and effectively a no-op until
      usage diverges — verify this is true and desired, not an oversight).

---

## 9. Phase 4 — Multi-sample reflection ensembling (fixes item 0.4)

**Goal:** reduce single-sample noise in the reflection signal, per the limitation your own
`docs/DEFENSE_GUIDE.md` already names.

**Changes:**
- [ ] Implement the primary design from §4: concurrent multi-sample reflection inside the
      existing `reflection_agent` pipeline slot. **Before writing code, do a short spike**:
      confirm google-adk's `Agent`/tool-calling model allows issuing N independent underlying
      Gemini calls from a single logical pipeline stage (e.g. via a custom `BaseAgent` subclass
      or a tool that itself fans out `google-genai` calls) without breaking `output_key` state
      propagation. Write down the spike's conclusion in the PR description even if the answer is
      "yes, straightforward."
- [ ] If the spike says the primary design is impractical, fall back to the `LoopAgent` +
      aggregator design from §4 — and if you do, treat updating `tests/test_pipeline.py`,
      `rca_system/agent.py`'s docstring/diagram, and `rca_system/ablations.py`'s
      `_clone_agent`/`build_root_agent` logic as **required parts of this phase**, not follow-up
      work.
- [ ] Make `reflection_ensemble_size` actually control the fan-out (already added to `settings`
      in Phase 0); confirm setting it to `1` reproduces exactly today's single-call behavior
      (useful for cheap local iteration and for demos where cost matters more than signal
      quality).
- [ ] Wire the two remaining Phase-0 diagnostic fields
      (`reflection_ensemble_agreement`) in `scripts/evaluate.py`.

**Tests:**
- [ ] Pure-Python aggregation unit tests (no Gemini needed — feed 3 mock sample outputs
      directly into the aggregation function): mean-of-proposed-deltas is correct when samples
      disagree on which incidents even got a delta; majority vote for `overall_quality`
      including the tie-break rule; a single wildly-different sample doesn't dominate the mean
      (add a test with one outlier among 3 samples and confirm the aggregate stays close to the
      other two, not pulled all the way to the outlier).
- [ ] Concurrency: confirm the 3 samples are actually issued concurrently, not sequentially
      (assert on wall-clock time in a test with a mocked, artificially-delayed call, or inspect
      that `asyncio.gather` — or the ADK equivalent — is actually used, not a `for` loop with
      `await` inside it).

**Checkpoint (live Gemini, real cost — budget for this):**
- [ ] Run `evaluate_memory_evolution.py` again on the existing dataset with the new ensembling
      active. Compare run-to-run variance for the *same* incidents against the Phase 2 checkpoint
      — the ensembled version should show less scenario-to-scenario noise in the deltas (you can
      eyeball this from the raw JSON's per-sample deltas before aggregation, which the
      diagnostic fields now expose).
- [ ] Confirm total token spend roughly 3× on the reflection stage specifically (not on the
      other three stages) — sanity-checks that the fan-out is scoped correctly.

**Critique checklist:**
- [ ] If one of the N concurrent calls raises (Gemini 503, timeout, malformed output), does the
      aggregation degrade gracefully (aggregate over the surviving samples) rather than crashing
      the whole pipeline run? Write a test that mocks one failing sample among three.
      This directly addresses the transient-503 failure mode already observed in your own
      `eval/experiments/SUMMARY-ablation-matrix.md` methodology note and `ragas-none-*.md`.
- [ ] Does `root_agent`'s structure still satisfy every assertion in `tests/test_pipeline.py`
      and every reference in `AGENTS.md` §6's pipeline table? If the primary (non-fallback)
      design was used, this should require zero changes to that table — confirm, don't assume.
- [ ] Re-read the cost trade-off honestly: is a 3× token increase on the single most expensive
      stage (reflection was already ~7.4K tokens/scenario) actually worth the noise reduction
      you measured? If the checkpoint doesn't show a clear improvement, say so in the PR
      description rather than shipping it uncritically — `reflection_ensemble_size` defaulting
      to `1` (i.e., effectively shipping the *capability* but not turning it on by default) is a
      legitimate outcome of this phase if the evidence doesn't support the cost.

---

## 10. Phase 5 — Bounded knowledge-base scale-up & full validation (fixes item 0.5)

**Goal:** de-risk the "k=5 of 6 touches almost everything" mechanical issue enough to trust the
Tier 0 result, without turning this PR into a content-authoring project.

**Changes:**
- [ ] Author 6–12 new incident files in `seed/incidents/`, following the exact frontmatter
      schema `scripts/seed_knowledge_base.py` requires (`incident_id, title, severity,
      root_cause, resolution, tags` + a markdown body — see `redis_connection_refused.md` as the
      template). Aim for genuinely distinct categories (not near-duplicates of the existing 6),
      so retrieval has real discrimination to do. Total KB size after this phase: ~12–18.
      **This is explicitly capped here — do not scale further in this PR; see §9 for the deferred
      full-scale version.**
- [ ] Create `eval/incidents_tier0_validation.jsonl` (new file — do **not** edit the canonical
      `eval/incidents.jsonl`, which stays untouched so the existing demo-ready 15-scenario set
      keeps working exactly as-is) with 2 in-domain scenarios per new incident (mirroring the
      existing paraphrase-robustness pattern) plus the existing 15 scenarios' equivalents against
      the larger KB.

**Tests:** no new unit tests expected in this phase; this is an evaluation/validation phase, not
a code-change phase. If the new incident content reveals a bug in Phases 1–4, fix it as an
explicit patch commit on this branch and note which earlier phase's checklist should have caught
it (feed that back into this document for the next tier).

**Checkpoint — this phase's checkpoint *is* the Tier 0 acceptance test:**
- [ ] `just reset-demo` against the expanded seed set (temporarily point `CHROMA_PERSIST_DIR` at
      a scratch dir, or use the eval scripts' own sandboxing — do not clobber your working demo
      KB while doing this).
- [ ] Run the full ablation matrix (`none, reflection_off, memory_frozen, no_rag, cot_only,
      retrieval_only, react`) via `scripts/evaluate.py --ablation <variant> --dataset
      eval/incidents_tier0_validation.jsonl` against the expanded KB. Use `--limit` smoke runs
      first to catch obvious breakage before spending the full budget.
- [ ] **Acceptance bar (write the actual numbers into this checklist when done):**
  - `none`'s retrieval MRR and nDCG@5 are within `0.05` of `memory_frozen`'s (ideally at or
    above it — the whole point of Tier 0 is closing this gap).
  - `none`'s keyword accuracy (exact-or-partial) is not the worst of the 7 variants.
  - No incident's `success_score` sits at the hard `0.0`/`2.0` clamp after this single
    validation run (a sign Phase 2's dampening is working at this larger scale).
  - `mean_top_retrieval_similarity` for in-domain scenarios does not regress versus the Phase 0
    baseline (sanity check that the larger, more diverse KB didn't just make everything harder
    to match for unrelated reasons, e.g. sloppily-written new incidents).

**Critique checklist:**
- [ ] Are the new incidents actually distinguishable from each other and from the original 6, or
      did you accidentally author near-duplicates that don't add real retrieval difficulty?
      Spot-check by embedding two new incidents and confirming their similarity to each other is
      lower than either's similarity to its own matching eval scenario.
- [ ] Did this phase accidentally mutate the production/demo ChromaDB directory
      (`rca-agent-system/data/chroma`)? Confirm the validation run used an isolated directory and
      run `just reset-demo` on the real one afterward regardless, to leave the repo in a clean
      demo-ready state for Phase 6.
- [ ] If the acceptance bar is **not** met after Phases 1–4, do not force it by re-tuning
      constants until the number looks right on this one dataset (that's overfitting to 18
      incidents). Instead, document the shortfall honestly in the PR description, and decide
      explicitly whether to (a) iterate on Phases 1–4's design, or (b) ship what's improved so
      far with the remaining gap noted as follow-up — both are legitimate, silently fudging the
      threshold is not.

---

## 11. Phase 6 — Full regression & PR assembly

**Goal:** make sure nothing outside the reflection/memory surface broke, and that the repo's own
documentation still tells the truth about how the system works.

**Changes:**
- [ ] `cd rca-agent-system && uv run pytest -q` — full pass, zero skips beyond the pre-existing,
      documented ones.
- [ ] `cd classifier-service && uv run pytest -q` and `cd frontend && pnpm test && pnpm build` —
      confirm untouched sub-projects genuinely are untouched (should pass trivially; if something
      fails here, Tier 0 leaked scope somewhere).
- [ ] Update documentation that describes the *old* mechanism as current behavior:
  - `AGENTS.md` §4 (env var table — add the 5 new settings) and §6 (tool/agent table — the
    delta-clamp description now needs the gating + pseudo-count nuance).
  - `docs/RESEARCH_QUESTIONS.md` RQ1/RQ3 "Evidence from a run" notes.
  - `docs/DEFENSE_GUIDE.md` — specifically the "How do you know score updates aren't random
    noise," "What stops a malicious or incorrect reflection from poisoning memory," and "What's
    the limitation of this approach you're most aware of" Q&As all need updated answers now that
    gating, capping, and ensembling exist (the last one especially — the *stated* limitation was
    "a stronger system would use multiple reflection samples and aggregate," which this tier
    directly implements).
  - `README.md` / `rca-agent-system/eval/README.md` — note the `just reset-demo` requirement.
- [ ] Run `just reset-demo` on the real dev environment one final time so the repo is left in a
      clean, demo-ready state.

**Definition of done for all of Tier 0:**
- [ ] All 6 phases' checkpoints recorded with actual numbers (not "looks good") in this file or
      the PR description.
- [ ] Phase 5's acceptance bar met, or explicitly and honestly not-met with a documented reason.
- [ ] Full test suite green across all three sub-projects.
- [ ] Exactly one PR opened, containing all 6 phases' commits, with a description that includes
      the before/after ablation-matrix table.
- [ ] Every "Critique checklist" box across every phase is checked or explicitly annotated with
      why it doesn't apply.

**Critique checklist (final, whole-tier):**
- [ ] Read the PR diff top to bottom as if you are the thesis examiner, not the author. Does it
      read as a coherent, well-motivated change, or as a pile of loosely-related tweaks?
- [ ] Is there anything in here that only works "on my machine" (hardcoded paths, an assumption
      about `data/chroma` being empty, an assumption about running from a specific working
      directory)? `rca-agent-system` is a standalone uv project — changes must work via `uv run`
      from that directory per `AGENTS.md`.
- [ ] Did scope creep in anywhere — e.g. did Phase 5 quietly grow past 12–18 incidents, or did
      Phase 4 quietly touch retrieval ranking? If yes, split it out before merging.

---

## 12. Explicitly out of scope / deferred (do not do these under Tier 0)

- Scaling the knowledge base to the full 50–200 incidents originally floated for item 0.5 — this
  is real, valuable follow-up work but is its own effort, not a Tier-0 sub-task.
- A runtime feature flag to toggle old-vs-new scoring behavior side by side — rejected in favor
  of clean per-phase commits as the rollback mechanism (§3, Round 1).
- Automatic migration/backfill of `alpha`/`beta` for pre-existing on-disk records — rejected in
  favor of documenting `just reset-demo` as a required post-upgrade step (§3, Round 1).
- Anything from Tiers 1–6 of the original improvement list (reranking, embedding-model upgrade,
  human-in-the-loop feedback, graph memory, etc.) — those are separate tiers with their own plans.

## 13. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Gemini doesn't reliably populate `used_incident_ids`, weakening Phase 1's gate | Medium | Phase 1's checkpoint explicitly audits this; if weak, strengthen `reasoning_agent.py`'s instruction as a noted, separate follow-up commit — don't silently work around it inside `record_reflection`. |
| ADK doesn't cleanly support in-slot multi-sampling (Phase 4) | Medium | Spike-first requirement in Phase 4; documented fallback design already specified. |
| Phase 5's acceptance bar isn't met even after Phases 1–4 | Medium | Explicitly allowed outcome (§10) — ship honestly, don't overfit constants to 18 incidents. |
| Rate limits make the Phase 5 full-matrix checkpoint impractical in one sitting | Medium | Use `--limit` smoke runs first; run the full matrix in off-peak stretches; it only needs to happen once per phase, not repeatedly. |
| Scope creep turns "one PR" into an unreviewable mega-diff | Low-Medium | §11's final critique checklist explicitly checks for this; phase commits keep it bisectable even if large. |
