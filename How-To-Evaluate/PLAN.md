# Evaluation Plan — Reflection-Enhanced Multi-Agent RAG for RCA

A prioritized catalogue of experiments to defend the project's claims with
real evidence beyond the current keyword-overlap + LLM-judge baseline.

Derived from:

- Our own docs: `docs/RESEARCH_QUESTIONS.md`, `docs/ARCHITECTURE_OVERVIEW.md`,
  `docs/DEFENSE_GUIDE.md` (the "Evaluation" Q&A section).
- The 9 supplied reference papers in `How-To-Evaluate/others/`.
- A focused literature scan (RAGAS, ARES, OpenRCA, LEMMA-RCA,
  MemoryAgentBench, Reflexion, GEMMAS, position-bias mitigation in
  LLM-judge).

Constraints applied throughout:

- **No human-eval** — only the researcher's own self-annotation counts.
- **Local compute only** — no GPU re-training, no large model swaps.

---

## 1. System under evaluation — what we have to defend

The four research-question claims, each traceable to specific code (full
trace in `docs/RESEARCH_QUESTIONS.md`):

| RQ | Claim | Where in code |
|----|---|---|
| RQ1 / RO1 | Reflection agent emits a useful per-incident relevance signal (deltas ∈ [-0.2, +0.2]) | `rca_system/agents/reflection_agent.py`, `tools/record_reflection.py` |
| RQ2 / RO3 | Four specialised agents > one generalist (auditable, testable) | `rca_system/agent.py` (`SequentialAgent`) |
| RQ3 / RO4 | `success_score` re-ranks retrieval; system learns without retraining | `chroma_store.update_score`, `retrieve_incidents` (`similarity × success_score`) |
| RQ4 / RO5 | Cheap classifier gate makes compute proportional to incident rate, not log volume | `classifier-service/app/classifier.py`, `useInvestigationsQueue.ts` |
| RO2 | Reflection → memory mutation → biased retrieval forms a closed loop | end-to-end state-key chain in `rca_system/agent.py` |

---

## 2. What we already measure

From `rca-agent-system/eval/README.md` and the existing scripts:

- **Quality.** Keyword-overlap (deterministic, `exact ≥0.66 / partial ≥0.33 / miss`)
  on the curated "Root cause" line. Optional LLM-judge (3-call majority via
  `--llm-judge`).
- **Retrieval.** `expected_incident_retrieval_recall` (in-domain only),
  top-hit cosine similarity.
- **Latency.** `mean_latency_s`, `p95_latency_s` per scenario.
- **Memory evolution.** Per-incident `baseline → run-1 → run-2`
  score table plus a `#boosted / #demoted / #unchanged` drift summary
  (`scripts/evaluate_memory_evolution.py`).
- **Dataset.** 15 scenarios in `eval/incidents.jsonl` (12 in-domain × 2
  paraphrases per seed incident + 3 OOD).
- **Classifier (separate notebook).** P / R / F1 on a BGL test split,
  but **not currently merged into the agent-pipeline eval reports**.

---

## 3. What the field considers rigorous — comparative matrix

What the four most-architecturally-relevant prior works do (✓ = yes; "—" = not done):

| Eval technique | Roy et al. (FSE'24 MS) | AutoBnB-RAG ('25) | IBM-RAG ('24) | OWL (ICLR'24) |
|---|---|---|---|---|
| Ablation study | ✓ (tool variants + retrieval budget) | ✓ (8 team structures, RAG-Wiki/News, k, chunk size) | ✓ (re-ranker on/off) | ✓ (HMCE on/off, MoA on/off) |
| Baseline comparison | ✓ (7 baselines: RB, CoT, IR-CoT, ReAct×3) | ✓ (no-RAG vs RAG-Wiki vs RAG-News) | ✓ (Google Search; multiple LLMs per stage) | ✓ (5 LLMs + 10 log-parsing baselines) |
| Lexical + semantic auto-metrics | ✓ (C/S-BLEU, ROUGE-L, METEOR, BERTScore) | — (binary win-rate only) | ✓ (BertScore, ROUGE-L) | ✓ (accuracy, F1, perplexity, RandIndex) |
| LLM-as-judge | — (replaced with manual coding) | — | — | ✓ (GPT-4 pairwise + single, bias-mitigation prompt) |
| Manual qualitative annotation | ✓ (2 annotators, 300 codings, discussion-based resolution) | ✓ (3 case-studies turn-by-turn) | ✓ (6 SMEs, 0–1 rubric) | ✓ (3 experts on training data only) |
| OOD / hold-out | ✓ (explicitly OOD test set) | — | ✓ (3 hold-out products) | ✓ (zero-shot + five-shot) |
| Multiple-runs / variance | — (single run, n=500) | ✓ (30 runs × 8 structures) | — | — (single run) |
| Statistical-significance tests | — | — | — | — |
| Public benchmark validation | — (private MS data) | ✓ (real-world breach reports) | — (private IBM data) | ✓ (LogHub: BGL, HDFS, Hadoop, …) |
| Latency / cost | mentioned, not quantified | — | — | training-compute only |
| Threats-to-validity section | ✓ (explicit) | — | ✓ (lessons-learned section) | — |

**What the consensus is:**

1. Ablation studies and baseline comparisons are **table-stakes** — every
   paper does both. We do neither right now.
2. Lexical metrics (ROUGE, BLEU, BERTScore) are **noisy alone** — every
   paper that uses them pairs them with either manual annotation, LLM-judge,
   or a stricter task metric. Our keyword-overlap is in the same family.
3. **Position bias in LLM-judge is real** (Zheng et al. 2024; multiple
   ACL'25 papers). OWL is the only one of our four that does bias mitigation
   (explicit "avoid positional / length bias" prompt + pairwise comparison).
4. **No paper does formal significance testing.** Effect sizes + multiple
   runs are the de facto substitute (AutoBnB-RAG: 30 runs).
5. **None of the four** does the "did the agent USE the retrieval correctly?"
   measurement that our reflection agent uniquely enables — this is a
   genuine novelty surface for us.

From the broader literature scan (Phase C):

- **RAGAS** (EACL'24) — three reference-free metrics that fit our setup:
  faithfulness (claims supported by context), answer relevancy
  (back-translation cosine similarity), context precision/recall.
- **ARES** (NAACL'24) — synthetic data + lightweight fine-tuned judges +
  prediction-powered inference. Too heavy for our scale but PPI is worth knowing.
- **Reflexion** (NeurIPS'23) — closest architectural prior art. Their
  ablation taxonomy is directly applicable: `NONE / LAST_ATTEMPT /
  REFLEXION / LAST_ATTEMPT_AND_REFLEXION`. We are a multi-agent variant of
  the `REFLEXION` arm; we should compare against the others.
- **MemoryAgentBench / EvoMemBench** — taxonomy for memory-agent eval:
  accurate retrieval, test-time learning, long-range understanding,
  selective forgetting. Maps cleanly onto our "did memory help?" question.
- **OpenRCA (ICLR'25, Microsoft) + LogHub** — public benchmarks we can run
  on without violating constraints. Best-in-class number (Claude 3.5)
  solves only 11.34% of OpenRCA; this is the SoTA bar for "RCA from
  telemetry" tasks.
- **Position-bias in LLM-as-judge** — mitigations: balanced permutation
  (swap A/B order), multiple samples, explicit "ignore length/position"
  instruction. Our current 3-call majority covers sampling but not order
  balancing.

---

## 4. Gaps in our current evaluation

A clean accounting before we propose experiments:

| Gap | Why it matters | Where we'll address it |
|---|---|---|
| No ablation study | Cannot attribute outcomes to reflection / memory / retrieval | Family 1 below |
| No baseline comparison | Cannot say multi-agent decomposition is worth the complexity | Family 2 |
| No statistical confidence on score-drift direction | Defense Q&A already calls this out | Family 3 (E3.1) |
| No "did memory help?" measurement | The novelty claim is currently shown via direction only, not utility | Family 3 (E3.5) |
| No adversarial memory test | Defense Q&A admits clamps are the only safeguard — never tested | Family 3 (E3.2) |
| Reflection itself unevaluated | We measure deltas, not whether the reflection's judgement is right | Family 4 (E4.3) |
| Keyword overlap is noisy | Punishes correct paraphrases; literature consensus is to pair with rubric / LLM-judge / manual | Family 4 (E4.1, E4.2, E4.3) |
| LLM-judge bias unmitigated | Position / length bias known issue; we do sampling but not order-balancing | Family 4 (E4.2) |
| Classifier metrics not in main eval | RQ4 (gating claim) currently qualitative | Family 7 |
| OOD set is only 3 scenarios | Defense Q&A admits this | Family 5 |
| No paraphrase / noise robustness | The "no close match" claim isn't stress-tested | Family 5 (E5.2, E5.3) |
| Cost-vs-volume claim not quantified | RQ4 needs a number | Family 6 (E6.3) |

---

## 5. Proposed experiments

Seven families, prioritized **P0 (must-do)**, **P1 (high-value)**,
**P2 (nice-to-have)**. Each experiment fits the "no human eval, local
compute" constraint. Effort estimates assume the existing eval
infrastructure is reused.

### Family 1 — Ablations (the user's original idea, refined)

The structural question: which components actually contribute? We
disable one at a time and re-run the in-domain eval (12 scenarios) and
the memory-evolution eval (2 runs of those 12).

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| **E1.1** | **Reflection-OFF** | Skip the reflection agent; memory-update agent does nothing. Re-run quality + memory-evolution. Compare to baseline. **Confirms reflection contributes a measurable signal.** | S | **P0** |
| **E1.2** | **Memory-FROZEN** | Reflection runs but its deltas are silently discarded; `success_score` stays at 1.0 forever. **Isolates whether the score-mutation mechanism (vs just having an extra agent) is what matters.** | S | **P0** |
| E1.3 | No re-rank | Set `success_score = 1.0` in `retrieve_incidents` so ranking is similarity-only. Quality should be ≈ E1.2 baseline. | S | P2 |
| **E1.4** | **No-RAG (no retrieval)** | Reasoning agent receives only the raw log chunk; no retrieval, no citations possible. **Quantifies the value of RAG over pure LLM reasoning.** | S | **P0** |
| **E1.5** | **Single-agent baseline** | One Gemini call with a long prompt that does retrieval-instruction + reasoning + reflection in one shot (no `SequentialAgent`). **Defends the multi-agent decomposition claim (RQ2).** | M | **P1** |
| E1.6 | Classifier-OFF | In monitoring mode, run RCA on every chunk regardless of classifier verdict; measure incremental cost. Directly evidences the gating claim (RQ4). | M | P1 |
| E1.7 | Embedding swap | `all-MiniLM-L6-v2 → all-mpnet-base-v2`. Optional curiosity ablation; not central to any claim. | S | P2 |

**Implementation note.** All Family-1 experiments are **prompt or
config flags**, not re-training. Implementing them as a `--ablation`
flag on `scripts/evaluate.py` and `scripts/evaluate_memory_evolution.py`
keeps the diff small.

**Output for the thesis.** One table per dataset:

| Variant | mean keyword score | exact / partial / miss | retrieval recall | mean latency | drift summary |
|---|---|---|---|---|---|

### Family 2 — Baseline comparisons (the "is this better than X?" question)

Roy et al. compare against 7 baselines. We should compare against at
least 3.

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| **E2.1** | **Retrieval-only baseline (RB)** | Top-k retrieval; return the top hit's summary as the "RCA" with no LLM call. Cheap, deterministic, zero-hallucination. This is the *floor* — anything we do must beat this. | S | **P0** |
| **E2.2** | **CoT-only baseline (no RAG)** | Same as E1.4 architecturally, but separately framed in the table as a "baseline" rather than an ablation. Helps Q&A: "is the LLM just good enough without our retrieval?". | S | **P0** |
| E2.3 | Reflexion-style single-agent | Single Gemini agent that calls retrieval, reasons, then verbally reflects in the same prompt context (no separate `SequentialAgent`, no per-incident scoring). This is the prior-art "verbal RL" baseline. Defends our multi-agent + numerical-score design over the 2023 Reflexion baseline. | M | P1 |
| E2.4 | Similarity-only RAG | Equivalent to E1.3 but framed as a baseline; isolates the value of `× success_score` re-ranking. | S | P2 |

### Family 3 — Memory evolution (the novelty)

This is the headline. The current `evaluate_memory_evolution.py` shows
drift direction; we need to upgrade it to defensible numbers.

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| **E3.1** | **Bootstrap CIs on drift direction** | Run the memory-evolution eval **5 times** (different temperature seeds for Gemini). Compute 95 % bootstrap CIs around `#boosted` and `#demoted`. If the CIs exclude "noise" (equal proportions), the direction is significant. | M | **P0** |
| **E3.2** | **Adversarial memory poisoning** | Manually craft a scenario whose ground-truth root cause matches one incident, but the reasoning agent is *prompted* to attribute it to a different (irrelevant) seeded incident. Run the pipeline. **Reflection should down-weight the wrong incident or refuse to boost it.** Validates the per-call clamp + reflection-as-safeguard claim. | M | **P0** |
| E3.3 | Negative-evidence test | Run the 3 OOD scenarios through the memory-evolution loop. Verify reflection emits small / zero deltas (not large boosts) for any retrieved incident. Validates RQ1's "fail honestly" behaviour. | S | P1 |
| E3.4 | Long-horizon drift | Run all 12 in-domain scenarios **5 times back-to-back**. Plot per-incident score trajectory. Expected: convergence within ~`[0.6, 1.6]`, not runaway towards 0 or 2 (the clamp). Validates stability. | M | P1 |
| **E3.5** | **"Did memory help?" — retrieval rank lift** | For each in-domain scenario, record the rank position of the expected incident in run-1 vs run-5. Compute **mean rank improvement**. If positive and statistically separable from zero, the memory loop measurably improves retrieval over time. This is the literature-gap experiment (MemoryAgentBench's "test-time learning" competency). | M | **P0** |

### Family 4 — End-to-end quality metrics (modern eval standard)

We currently use keyword-overlap + optional LLM-judge. The field has
moved on; we should adopt a richer (still automated) suite.

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| **E4.1** | **RAG triad (RAGAS-style)** | Implement three reference-free metrics with Gemini-as-judge for the 15 scenarios: (a) **faithfulness** — fraction of claims in the final report that are supported by the retrieved incidents; (b) **answer relevancy** — cosine-sim between original chunk and 3 back-translated questions generated from the report; (c) **context precision** — fraction of retrieved incidents that the reasoning agent actually cited. Replicates RAGAS without taking on the dependency. | L | **P0** |
| **E4.2** | **Pairwise LLM-judge with bias mitigation** | Pairwise rather than single-score. For each (variant A, variant B) pair: 3 Gemini calls with positions A/B; 3 more with B/A. Aggregate by 6-call majority with explicit "ignore position and length" instruction (OWL paper template). Reduces position bias documented in Zheng et al. 2024. | M | **P0** |
| **E4.3** | **Self-annotation with Roy et al. coding scheme** | You (the researcher) annotate the 15-scenario outputs of each ablation variant with the Roy et al. categories: `Correct-Precise / Correct-Imprecise / Hallucination (correct OR incorrect) / Insufficient-Evidence / Reasoning-Error / Reflection-Error / Retrieval-Error / Other`. Report accuracy + hallucination rate per variant. **Fits the no-human-eval constraint because self-annotation by the researcher is not "external human eval".** | M | **P0** |
| E4.4 | Retrieval metrics: Recall@k, MRR, nDCG | Compute the standard IR triad over the 6-incident KB. We have `expected_incident_id` ground truth in the dataset. nDCG with binary relevance is sufficient given the small KB. | S | P1 |

**Important.** E4.3 is the answer to "How do we get rigour without
external annotators?" Roy et al.'s methodology — single annotator with
structured coding categories + transparent discussion of disagreements
— is acceptable for a thesis if (a) the coding scheme is published in
advance, (b) the annotations are released so an auditor could replay
them, (c) the annotator declares their bias.

### Family 5 — Robustness / OOD

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| E5.1 | OOD low-confidence reporting | For the 3 OOD scenarios, add a derived metric: `top_similarity < 0.5` → "low-confidence" flag. Verify the system reports low confidence rather than confabulating a citation. | S | P1 |
| **E5.2** | **Paraphrase robustness** | Use Gemini to generate 5 paraphrased variants per in-domain scenario (controlled prompt). For each scenario, run all 5 and measure agreement of (a) retrieved incident IDs, (b) extracted root cause keyword set. Target ≥ 80 % agreement. | M | **P1** |
| E5.3 | Noise injection | Interleave 3 unrelated INFO-level log lines between the ERROR lines in each scenario. Re-evaluate quality. Measures distractor robustness. | S | P2 |
| E5.4 | Eindhoven coverage audit | Classify each of the 15 scenarios under the Eindhoven model (Williams 2001, BUMC) — Technical / Organizational / Human / Rule-based / Knowledge-based. Identifies which RCA category families our KB does and does not cover. Honest limitation reporting. | S | P2 |

### Family 6 — Operational metrics

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| E6.1 | Per-stage latency breakdown | Already measured at total-pipeline level. Add per-stage timers (classifier, retrieval, reasoning, reflection, memory_update) and report. | S | P1 |
| E6.2 | Token cost per RCA | Count input + output tokens per Gemini call. Mean ± std across the 15 scenarios. Pulls a number out of the qualitative cost-claim. | S | P1 |
| **E6.3** | **Cost-vs-volume simulation (RQ4)** | Simulate a 1000-chunk stream with 5 % incident rate (50 ERROR/FATAL + 950 NORMAL/WARNING). Count total Gemini calls under (a) gated (our system) and (b) ungated (RCA on every chunk). Report ratio. **The headline number for the RQ4 claim.** | M | **P0** |
| E6.4 | Memory storage growth | Plot ChromaDB DB size after 1, 5, 10, 20 pipeline runs. Confirms `success_score` updates don't bloat the store. | S | P2 |

### Family 7 — Classifier (gate)

| ID | Experiment | Method | Effort | Priority |
|---|---|---|---|---|
| **E7.1** | **Classifier P/R/F1 in main eval report** | The training notebook already computes this on a BGL test split. Lift the numbers into the main pipeline eval report so it appears alongside the agent metrics. **Closes the RQ4 evidence gap.** | S | **P0** |
| E7.2 | Calibration (ECE on BGL) | Add an Expected Calibration Error column. Does `confidence` predict correctness? Reliability diagram for the appendix. | S | P1 |
| E7.3 | Public LogHub benchmark validation | Run the classifier on a held-out slice of LogHub BGL (which we already have access to) using OWL's protocol (Table 6 of the OWL paper). Compare F1 to LogPrompt (the published ChatGPT-based baseline ≈ 0.384). | M | P1 |
| E7.4 | Gate-correctness on the eval set | For each chunk in `incidents.jsonl`, record `should_invoke_rca` from the classifier. Correlate against whether the agent pipeline produced a non-trivial RCA. False-positive cost = wasted Gemini calls; FN cost = missed incidents. | S | P1 |

---

## 6. Priority summary

The **P0 set** (8 experiments) is the minimum we should run for the
thesis defense — it covers every flagged gap and every RQ claim:

| Family | P0 | What it defends |
|---|---|---|
| Ablations | E1.1 (Reflection-OFF), E1.2 (Memory-FROZEN), E1.4 (No-RAG) | RQ1, RQ2, RO2 |
| Baselines | E2.1 (Retrieval-only), E2.2 (CoT-only) | RQ2 |
| Memory | E3.1 (Bootstrap CIs), E3.2 (Adversarial poisoning), E3.5 (Rank lift) | RQ3, RO2 |
| Quality | E4.1 (RAGAS triad), E4.2 (Pairwise judge), E4.3 (Self-annotation) | RQ1, RQ2 |
| Operational | E6.3 (Cost-vs-volume) | RQ4 |
| Classifier | E7.1 (P/R/F1 in main report) | RQ4 |

Total P0 effort: ~5 working days if you parallelize prompt-config work
and analysis; longer if you also re-baseline.

**P1 set** (10 experiments): E1.5, E1.6, E2.3, E3.3, E3.4, E4.4, E5.1,
E5.2, E6.1, E6.2, E7.2, E7.3, E7.4. Each is high value but the thesis
defense is defensible without them.

**P2 set** (8 experiments): E1.3, E1.7, E2.4, E5.3, E5.4, E6.4 — fill
out the appendix; not on the critical path.

---

## 7. Suggested execution order

Sequenced for **reuse of effort** — earlier experiments produce
infrastructure later ones depend on:

1. **Plumbing first (~1 day).** Add `--ablation {reflection_off, memory_frozen, no_rag, ...}` flags to `evaluate.py` and `evaluate_memory_evolution.py`. Add per-stage timers (E6.1). Add token-counting (E6.2). Add Recall@k/MRR/nDCG computation (E4.4).
2. **Run the ablation matrix once (~half a day of wall clock, mostly Gemini latency).** E1.1, E1.2, E1.4, E1.5. Output: one summary table.
3. **Run the baseline matrix once (~half a day).** E2.1, E2.2.
4. **Quality metrics in parallel (~1 day, mostly Gemini calls).** E4.1 (RAGAS triad), E4.2 (pairwise judge), E4.3 (self-annotation — this one is *your* time, allow 2–3 h).
5. **Memory experiments (~1–2 days, lots of Gemini).** E3.1 (5 runs of memory-evolution), E3.2 (single crafted scenario), E3.5 (rank-lift over 5 runs).
6. **Operational closer (~half a day).** E6.3 (simulation, no Gemini), E7.1 (lift existing numbers), then any P1 robustness experiments you want.

Total: **~5–7 working days** end-to-end for the P0 set, assuming Gemini
quota is the binding constraint (it is — free tier ≈ 15 RPM, P0 needs
~600 Gemini calls).

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gemini rate-limits during 5-run bootstrap | High | Stalls experiments | Cache intermediate results; use `--limit` to smoke-test before full runs; run overnight |
| Ablation reveals reflection adds < 5 % quality | Medium | Weakens RQ1 claim | This is what the experiment is *for* — report honestly. Reframe RQ1 as "reflection provides a memory-shaping signal" (a softer claim that's still defensible if E3.5 is positive). |
| Memory-evolution direction is noise once we add CIs | Medium | Hard for RQ3 | E3.5 (rank lift) is independent evidence; if E3.1 shows noise but E3.5 shows lift, the loop still has utility |
| Self-annotation (E4.3) accused of bias | Medium | Methodology critique | Publish the coding scheme in advance; release the annotation CSV; declare bias in writeup (Roy et al. methodology) |
| Classifier OOD on LogHub (E7.3) shows poor F1 | Medium | Evidence the classifier doesn't generalize | This is honest limitation reporting. The training data is BGL; testing on Spirit shows the BGL-specific tuning |
| RAGAS-style faithfulness metric (E4.1) flags many hallucinations | Low (we cite by reference) | Could be embarrassing | Run on a 3-scenario subset first; if rate is high, debug citation prompts before running the full suite |

---

## 9. What lives outside this plan (and why)

- **External human evaluation** (the user-study protocol from
  Toro Isaza et al.). Excluded by your constraint.
- **GPU re-training of the classifier** (e.g., distilling to a smaller
  model, trying different base models). Excluded by your local-compute
  constraint. The classifier's existing P/R/F1 is sufficient for the
  thesis.
- **OpenRCA (ICLR'25) full benchmark.** 68 GB of telemetry, 335 cases,
  needs 32 GB RAM + 80 GB storage and a different agent contract (Python
  data analysis tool, not log chunks). Out of scope; mention as future
  work if asked.
- **RCAEval / LEMMA-RCA / ops-lite.** Microservice-telemetry-flavoured
  RCA benchmarks. Same scope issue. Future work.
- **Production deployment metrics** (real on-call engineer feedback,
  ticket-resolution latency reduction). Requires a deployed product;
  out of thesis scope.

---

## 10. Open questions for you

These are the choices to make before we start executing P0:

1. **How tight is your timeline?** If P0 must fit in < 3 days, drop
   E3.1 (bootstrap CIs) and run memory-evolution once with seeds 0..2 only.
2. **Do you want RAGAS as a hard dependency, or re-implement just the
   three metrics ourselves?** Re-implementing in ~150 LoC keeps things
   light and avoids adding a transitive `langchain` dependency.
3. **For E4.3 (self-annotation): are you OK doing it yourself, or do
   you want me to write a CLI annotator that walks you through 15 × 5
   = 75 outputs in ~2 hours?** I recommend the CLI annotator — it
   forces the structured coding scheme and produces a reproducible
   CSV.
4. **Should the experiment scripts write to `eval/` (same as today) or
   to a new `eval/experiments/` folder so we don't clobber the existing
   demo-ready reports?** I recommend the latter.

When you've decided which experiments to run, I'll start with the
plumbing pass (step 1 in §7) and then knock through P0 sequentially.

---

## 11. Decision log

Choices made on 2026-05-24 to bound execution:

| Question | Decision |
|---|---|
| Scope | **P0 only** — the 13-experiment must-do set (≈ 5–7 working days). |
| E4.3 annotation UX | **Build a CLI annotator** — a Python tool that walks the researcher through ~75 outputs with the structured Roy-et-al. coding scheme; emits a reproducible CSV. |
| Output location | `rca-agent-system/eval/experiments/` — kept separate from the demo-ready `eval/results-*.md` and `eval/memory-evolution-*.md`. |
| RAGAS implementation | **Re-implement the three metrics ourselves (~150 LoC)** — no new transitive dependency, full control over prompts, easier to integrate with the existing `--llm-judge` Gemini call style. |

Choices made on 2026-05-29:

| Question | Decision |
|---|---|
| Day-1 plumbing scope | **Done** — `--ablation {none,reflection_off,memory_frozen,no_rag,cot_only,retrieval_only}` on both eval scripts (factory in `rca_system/ablations.py`), per-stage latency + token counting, retrieval IR triad (Recall@k/MRR/nDCG), outputs routed to `eval/experiments/`. |
| E4.3 | **Deferred** for now (no self-annotation pass yet); other automated P0 experiments proceed. |
| Rate-limit handling | **Retry-on-429** during the real runs (assume quota is sufficient / paid tier). |
| In-product eval UI | **Build it** (see §12). Each experiment gets its own page describing what it evaluates (plain + technical), a re-run control, live progress, and rendered results. |

### Concrete next-action queue

The P0 set, sequenced for incremental review:

1. **Plumbing pass (`Day 1`).** ✅ **Done.** `--ablation` flag on both scripts,
   per-stage timers, token counting, retrieval IR metrics (E4.4 compute),
   `eval/experiments/` directory + README.
2. **Evaluation UI (`§12`).** ⏳ In progress — in-product console so every
   experiment is browsable, re-runnable, and self-describing.
3. **Ablation matrix (`Day 2`).** Run E1.1, E1.2, E1.4 + the two baselines E2.1, E2.2 — produces one comparative table. (Runnable via CLI **or** the new UI.)
4. **Quality metrics (`Day 3`).** Implement the RAGAS triad (E4.1) and the pairwise-with-bias-mitigation judge (E4.2). (E4.3 deferred.) Run on the ablation outputs.
5. **Memory experiments (`Day 4–5`).** E3.1 (5-run bootstrap), E3.2 (craft the adversarial scenario), E3.5 (rank-lift over the 5 runs).
6. **Operational + classifier closers (`Day 6`).** E6.3 (cost-vs-volume sim, no Gemini needed), E7.1 (lift the classifier P/R/F1 into the main report).
7. **Writeup (`Day 7`).** Consolidate everything in `eval/experiments/SUMMARY.md` with the thesis-ready table per RQ.

---

## 12. Family 8 — In-product evaluation console (UI)

A new **Evaluation** tab in the Next.js frontend. The motivation: the
thesis defense is far more convincing if every experiment can be
re-run live and explains itself, rather than being a pile of CLI scripts
and markdown files. This is an **evaluation-infrastructure** family, not
a new research claim — it surfaces Families 1–7 to the operator.

### Requirements

- A dedicated tab; one page per experiment.
- Each page describes, in **plain English and technical terms**, what the
  experiment evaluates and which RQ/RO it defends.
- A **re-run** control with tunable parameters (e.g. `--limit`,
  `--llm-judge`, ablation variant is fixed per card).
- **Live progress** while a run executes.
- **Rendered results** (summary metrics + per-scenario table) and a
  **history** of past runs.
- New experiments must slot in **without frontend changes**.

### Architecture decisions (locked 2026-05-29)

| Decision | Choice | Rationale |
|---|---|---|
| Execution model | **Subprocess** — the server spawns `uv run python scripts/...` | Isolation; doesn't block the live server event loop; cancellable; exactly reproduces the CLI. |
| KB isolation | **Sandbox per run** — `CHROMA_PERSIST_DIR=./data/eval-runs/<job>`, seeded fresh | Eval runs mutate `success_score`; sandboxing keeps the live/demo memory untouched and runs reproducible. |
| Run gating | **None** — runs are always allowed, but **single-flight** (one at a time) | Gemini rate limits + sandbox seeding make concurrent runs unsafe; a 409-on-busy lock suffices. |
| Progress transport | **Polling** (`GET /eval/jobs/{id}`, ~2 s) | Per-scenario cadence is ~30–60 s; polling is simpler and reconnection-safe. |
| Card scope | **Runnable + planned** | Implemented experiments are runnable; not-yet-built P0 experiments show as disabled "planned" cards so the console tells the whole story. |

### Single source of truth: the experiment registry

`rca_system/eval_api/registry.py` declares every experiment:
`id, title, rq_tags, family (PLAN id), summary, description_plain,
description_technical, command, params_schema, gemini_cost_note,
expected_runtime, outputs_glob, status (runnable|planned)`. The UI renders
cards and detail pages entirely from this registry, so adding an
experiment later is a one-entry change (plus a script if it's new).

### Backend (`rca-agent-system`)

```
rca_system/eval_api/
  registry.py   # experiment metadata + param schemas
  jobs.py       # JobManager: single-flight subprocess runner, sandbox seed,
                # status/log tail, cancel; mirrors state to eval/experiments/.jobs/
  routes.py     # APIRouter, included from server.py
```

Endpoints: `GET /eval/experiments`, `GET /eval/experiments/{id}`,
`POST /eval/experiments/{id}/run` (409 if busy), `GET /eval/jobs[/{id}]`,
`POST /eval/jobs/{id}/cancel`, `GET /eval/results/{id}/{file}`
(path-traversal-guarded to `eval/experiments/`). The eval scripts gain a
`--progress-json` flag that emits one JSON line per lifecycle event
(`run_start`/`scenario_done`/`run_done`) for the runner to surface.

### Frontend (`frontend`, Next.js 16)

- Nav entry **"Evaluation"**; `/evaluation` landing (cards grouped by
  RQ/family) and `/evaluation/[id]` detail (descriptions, params form, run
  controls, polling progress, results, history).
- `src/lib/api/evaluation.ts` (mirrors `agents.ts`), hooks
  `useExperiments` / `useExperimentRun` / `useEvalResults`, components under
  `src/components/evaluation/`. Vitest + jsdom tests with `vi.mock`.

### Phasing

- **U0** docs (this section + AGENTS.md). **U1** backend (registry, jobs,
  routes, `--progress-json`, tests). **U2** frontend landing + client/hook
  + nav. **U3** detail page (params, run, polling). **U4** results +
  history. **U5** static classifier-metrics card (E7.1).

This plan is **active** — Day-1 plumbing is done; the evaluation UI (§12)
is being built before the Day-2 ablation matrix so the matrix can be run
from the console.
