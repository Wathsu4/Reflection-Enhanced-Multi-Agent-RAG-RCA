"""Declarative registry of evaluation experiments.

This is the **single source of truth** for the evaluation console. Each
`Experiment` carries everything the UI needs to render a self-describing
card + detail page (plain-English and technical descriptions, RQ tags,
the PLAN.md family id, tunable parameters) and everything the job runner
needs to actually execute it (which script, fixed args, how to build the
arg list from user params).

Adding an experiment later is a one-entry change here (plus a script if
the experiment is genuinely new). The frontend needs no changes.

Mapping to `How-To-Evaluate/PLAN.md`:
  * runnable today  -> the Day-1 plumbing already supports them
  * status="planned" -> P0 experiments not yet implemented; shown as
    disabled cards so the console tells the whole evaluation story.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Which underlying script a runnable experiment drives. `None` => not
# runnable (a planned card).
ScriptName = Literal[
    "evaluate",
    "memory_evolution",
    "classifier_metrics",
    "ragas",
    "pairwise",
    "cost_vs_volume",
]
ExperimentStatus = Literal["runnable", "planned"]


class ParamSpec(BaseModel):
    """A single user-tunable parameter exposed as a form field in the UI."""

    name: str
    label: str
    kind: Literal["int", "bool"]
    cli_flag: str
    default: int | bool
    help: str = ""
    # int-only bounds (ignored for bools); used for client + server validation.
    minimum: int | None = None
    maximum: int | None = None

    def coerce(self, value: Any) -> int | bool:
        """Validate + coerce a raw param value from an API request."""
        if self.kind == "bool":
            return bool(value)
        try:
            ivalue = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{self.name} must be an integer") from exc
        if self.minimum is not None and ivalue < self.minimum:
            raise ValueError(f"{self.name} must be >= {self.minimum}")
        if self.maximum is not None and ivalue > self.maximum:
            raise ValueError(f"{self.name} must be <= {self.maximum}")
        return ivalue

    def to_args(self, value: int | bool) -> list[str]:
        """Render this param as CLI args. Bools are store_true flags."""
        if self.kind == "bool":
            return [self.cli_flag] if value else []
        return [self.cli_flag, str(value)]


class Experiment(BaseModel):
    """One evaluation experiment, fully self-describing."""

    id: str
    title: str
    summary: str
    description_plain: str
    description_technical: str
    rq_tags: list[str] = Field(default_factory=list)
    family: str = ""  # PLAN.md id, e.g. "E1.1"
    status: ExperimentStatus = "runnable"

    # Execution (ignored when status="planned").
    script: ScriptName | None = None
    base_args: list[str] = Field(default_factory=list)
    params: list[ParamSpec] = Field(default_factory=list)
    # Glob (relative to the `eval/` dir) used to find this experiment's
    # past result files for the history list.
    outputs_glob: str = ""

    gemini: bool = True
    gemini_cost_note: str = ""
    expected_runtime: str = ""

    def build_command_args(self, raw_params: dict[str, Any] | None = None) -> list[str]:
        """Build the script arg list (excluding the python/script prefix and
        `--progress-json`, which the job runner adds) from user params.

        Unknown params are ignored; missing params fall back to defaults.
        Raises `ValueError` on out-of-range / mistyped values.
        """
        raw = raw_params or {}
        args = list(self.base_args)
        for spec in self.params:
            value = raw[spec.name] if spec.name in raw else spec.default
            args.extend(spec.to_args(spec.coerce(value)))
        return args


# -------------------- shared parameter specs --------------------

_LIMIT_PARAM = ParamSpec(
    name="limit",
    label="Scenario limit",
    kind="int",
    cli_flag="--limit",
    default=0,
    minimum=0,
    maximum=15,
    help="Run only the first N scenarios (0 = all 15). Use a small value "
    "for a quick smoke test.",
)

_LLM_JUDGE_PARAM = ParamSpec(
    name="llm_judge",
    label="LLM-as-judge",
    kind="bool",
    cli_flag="--llm-judge",
    default=False,
    help="Add a Gemini-as-judge verdict per scenario (3-call majority). "
    "Slower and uses extra Gemini quota.",
)

_RUNS_PARAM = ParamSpec(
    name="runs",
    label="Runs over the set",
    kind="int",
    cli_flag="--runs",
    default=2,
    minimum=1,
    maximum=5,
    help="How many times to iterate the in-domain set. More runs give a "
    "clearer drift trend but cost more Gemini calls.",
)


# -------------------- the catalogue --------------------

EXPERIMENTS: list[Experiment] = [
    # ---- Full system ----
    Experiment(
        id="pipeline-full",
        title="Full pipeline — accuracy, latency & retrieval",
        summary="The complete 4-agent system on all 15 scenarios.",
        description_plain=(
            "Runs the whole root-cause-analysis system exactly as it ships: "
            "it looks up similar past incidents, reasons about the likely "
            "cause, double-checks its own answer, and updates its memory. "
            "We then check how often its answer matches the known correct "
            "cause, how long it takes, and whether it found the right past "
            "incident."
        ),
        description_technical=(
            "Executes the production `SequentialAgent` (retrieval → reasoning "
            "→ reflection → memory_update) over `eval/incidents.jsonl` via "
            "ADK's in-process Runner. Reports keyword-overlap verdicts "
            "(exact/partial/miss), optional Gemini LLM-judge, per-stage "
            "latency, Gemini token usage, and the retrieval IR triad "
            "(Recall@k / MRR / nDCG@k) over the 12 in-domain scenarios."
        ),
        rq_tags=["RQ1", "RQ2", "RQ3", "RO2"],
        family="baseline",
        script="evaluate",
        base_args=["--ablation", "none"],
        params=[_LIMIT_PARAM, _LLM_JUDGE_PARAM],
        outputs_glob="results-*.json",
        gemini_cost_note="~4 Gemini calls/scenario (+3/scenario with LLM-judge).",
        expected_runtime="~8–12 min for all 15 (Gemini-bound).",
    ),
    # ---- Ablations ----
    Experiment(
        id="ablation-reflection-off",
        title="Ablation: reflection OFF",
        summary="Drop the reflection stage; measure the quality delta.",
        description_plain=(
            "Runs the system with the 'self-critique' step removed. The "
            "system still retrieves past incidents and reasons about them, "
            "but no longer scores how useful each retrieved incident was, so "
            "its memory never updates. Comparing this to the full system "
            "shows whether the reflection step actually earns its place."
        ),
        description_technical=(
            "Pipeline = retrieval → reasoning → memory_update (no reflection "
            "agent). memory_update receives no deltas, so `success_score` is "
            "never mutated. Isolates the contribution of the reflection "
            "signal (RQ1) and its role in the closed loop (RO2)."
        ),
        rq_tags=["RQ1", "RO2"],
        family="E1.1",
        script="evaluate",
        base_args=["--ablation", "reflection_off"],
        params=[_LIMIT_PARAM, _LLM_JUDGE_PARAM],
        outputs_glob="experiments/results-reflection_off-*.json",
        gemini_cost_note="~3 Gemini calls/scenario.",
        expected_runtime="~6–10 min for all 15.",
    ),
    Experiment(
        id="ablation-memory-frozen",
        title="Ablation: memory FROZEN",
        summary="Reflection runs, but score writes are suppressed.",
        description_plain=(
            "Runs the full system including the self-critique step, but "
            "secretly throws away the memory updates it produces — the "
            "memory's usefulness scores stay fixed forever. This separates "
            "'having an extra agent' from 'actually learning over time'."
        ),
        description_technical=(
            "Full pipeline, but memory_update uses a no-op apply tool: the "
            "reflection agent still emits deltas, yet `success_score` is "
            "never written. Isolates the score-mutation mechanism (RQ3) from "
            "the mere presence of the reflection agent."
        ),
        rq_tags=["RQ3", "RO2"],
        family="E1.2",
        script="evaluate",
        base_args=["--ablation", "memory_frozen"],
        params=[_LIMIT_PARAM, _LLM_JUDGE_PARAM],
        outputs_glob="experiments/results-memory_frozen-*.json",
        gemini_cost_note="~4 Gemini calls/scenario.",
        expected_runtime="~8–12 min for all 15.",
    ),
    Experiment(
        id="ablation-no-rag",
        title="Ablation: no retrieval (no RAG)",
        summary="Reason from the raw log alone — no past incidents.",
        description_plain=(
            "Runs the system with its memory lookup switched off, so it must "
            "diagnose each incident purely from the raw log lines with no "
            "help from similar past cases. Comparing to the full system "
            "quantifies how much the retrieval-augmented memory is worth."
        ),
        description_technical=(
            "Pipeline = reasoning → memory_update, with no retrieval stage. "
            "The reasoning agent sees an empty `retrieval_output` and cannot "
            "cite any prior incident. Quantifies the value of RAG over pure "
            "LLM reasoning (RQ2)."
        ),
        rq_tags=["RQ2"],
        family="E1.4",
        script="evaluate",
        base_args=["--ablation", "no_rag"],
        params=[_LIMIT_PARAM, _LLM_JUDGE_PARAM],
        outputs_glob="experiments/results-no_rag-*.json",
        gemini_cost_note="~2 Gemini calls/scenario.",
        expected_runtime="~5–8 min for all 15.",
    ),
    # ---- Baselines ----
    Experiment(
        id="baseline-retrieval-only",
        title="Baseline: retrieval-only (no LLM)",
        summary="Return the closest past incident verbatim. Zero LLM.",
        description_plain=(
            "The simplest possible 'system': just find the single most "
            "similar past incident and report its known root cause, with no "
            "language-model reasoning at all. This is the floor — anything "
            "the real system does must beat this to justify its complexity. "
            "It makes no Gemini calls, so it is fast and free."
        ),
        description_technical=(
            "Deterministic top-k retrieval with the production "
            "`similarity × success_score` re-ranking; the top hit's stored "
            "root_cause becomes the answer. No Gemini call. Establishes the "
            "zero-hallucination retrieval floor (E2.1) and exercises the IR "
            "metrics independent of the LLM."
        ),
        rq_tags=["RQ2"],
        family="E2.1",
        script="evaluate",
        base_args=["--ablation", "retrieval_only"],
        params=[_LIMIT_PARAM],
        outputs_glob="experiments/results-retrieval_only-*.json",
        gemini=False,
        gemini_cost_note="No Gemini calls — deterministic and fast.",
        expected_runtime="< 30 s for all 15.",
    ),
    Experiment(
        id="baseline-cot-only",
        title="Baseline: chain-of-thought only (no RAG)",
        summary="One LLM reasoning pass on the raw log, framed as a baseline.",
        description_plain=(
            "Asks the language model to diagnose each incident from the raw "
            "log alone, with no memory lookup — the classic 'just ask the "
            "model' approach. Framed as a baseline (rather than an ablation) "
            "to answer the question: is the LLM already good enough without "
            "our retrieval and memory?"
        ),
        description_technical=(
            "Architecturally identical to `no_rag` (reasoning → "
            "memory_update, no retrieval) but reported as a baseline (E2.2). "
            "Lets the thesis contrast the full RAG+memory system against a "
            "plain chain-of-thought LLM."
        ),
        rq_tags=["RQ2"],
        family="E2.2",
        script="evaluate",
        base_args=["--ablation", "cot_only"],
        params=[_LIMIT_PARAM, _LLM_JUDGE_PARAM],
        outputs_glob="experiments/results-cot_only-*.json",
        gemini_cost_note="~2 Gemini calls/scenario.",
        expected_runtime="~5–8 min for all 15.",
    ),
    # ---- Memory evolution (the novelty) ----
    Experiment(
        id="memory-evolution",
        title="Memory evolution (headline novelty)",
        summary="Score drift across repeated runs over the in-domain set.",
        description_plain=(
            "The headline experiment. Starts every past incident at a neutral "
            "usefulness score, then runs the in-domain cases through the "
            "system several times. Incidents the system correctly leans on "
            "should drift upward; ones it retrieves but ignores should drift "
            "down. This demonstrates the system learning from its own "
            "feedback without any retraining."
        ),
        description_technical=(
            "Resets ChromaDB to seed (all `success_score`=1.0), then runs the "
            "12 in-domain scenarios through the full pipeline N times, "
            "snapshotting scores between runs. Emits a per-incident "
            "baseline → run-1 → … → run-N table plus a "
            "boosted/demoted/unchanged drift summary (RQ3, RO2)."
        ),
        rq_tags=["RQ3", "RO2"],
        family="E3 / E3.x",
        script="memory_evolution",
        base_args=["--ablation", "none"],
        params=[_RUNS_PARAM, _LIMIT_PARAM],
        outputs_glob="memory-evolution-*.md",
        gemini_cost_note="~4 Gemini calls × 12 scenarios × N runs.",
        expected_runtime="~10–20 min for 2 runs (Gemini-bound).",
    ),
    Experiment(
        id="memory-evolution-reflection-off",
        title="Memory evolution — reflection OFF (control)",
        summary="Control: scores should stay flat with no reflection.",
        description_plain=(
            "A control for the headline experiment: repeats it with the "
            "self-critique step removed. With nothing producing memory "
            "updates, the usefulness scores should stay flat — confirming "
            "that the drift seen in the real experiment is caused by "
            "reflection, not by chance."
        ),
        description_technical=(
            "Same as memory-evolution but with `--ablation reflection_off`, "
            "so no deltas are produced and `success_score` should not move. "
            "Negative control for RQ3 / RO2."
        ),
        rq_tags=["RQ3", "RO2"],
        family="E1.1 / E3",
        script="memory_evolution",
        base_args=["--ablation", "reflection_off"],
        params=[_RUNS_PARAM, _LIMIT_PARAM],
        outputs_glob="experiments/memory-evolution-reflection_off-*.md",
        gemini_cost_note="~3 Gemini calls × 12 scenarios × N runs.",
        expected_runtime="~8–16 min for 2 runs.",
    ),
    Experiment(
        id="memory-evolution-memory-frozen",
        title="Memory evolution — memory FROZEN (control)",
        summary="Control: reflection runs but writes are suppressed.",
        description_plain=(
            "Another control: the self-critique step runs and produces "
            "memory updates, but those updates are thrown away. Scores should "
            "stay flat, proving the drift in the real experiment comes from "
            "actually persisting the updates."
        ),
        description_technical=(
            "Same as memory-evolution but with `--ablation memory_frozen`: "
            "reflection emits deltas yet the apply step is a no-op. Isolates "
            "persistence from signal generation (RQ3)."
        ),
        rq_tags=["RQ3", "RO2"],
        family="E1.2 / E3",
        script="memory_evolution",
        base_args=["--ablation", "memory_frozen"],
        params=[_RUNS_PARAM, _LIMIT_PARAM],
        outputs_glob="experiments/memory-evolution-memory_frozen-*.md",
        gemini_cost_note="~4 Gemini calls × 12 scenarios × N runs.",
        expected_runtime="~10–20 min for 2 runs.",
    ),
    # ---- Planned (P0, not yet implemented) ----
    Experiment(
        id="ragas-triad",
        title="RAG triad (faithfulness / relevancy / context precision)",
        summary="Reference-free RAG quality metrics, Gemini-judged.",
        description_plain=(
            "A modern way to grade RAG answers without a fixed answer key: "
            "checks whether the report's claims are actually supported by the "
            "retrieved incidents (faithfulness), whether it answers the log "
            "it was given (relevancy), and whether the incidents it cited "
            "were the relevant ones (context precision)."
        ),
        description_technical=(
            "RAGAS-style triad re-implemented locally with Gemini-as-judge: "
            "faithfulness (claims grounded in retrieved context), answer "
            "relevancy (cosine between the log chunk and questions "
            "back-generated from the report), context precision (rank-aware "
            "average precision of retrieved vs cited incidents -- "
            "deterministic). Runs the full pipeline then scores it (E4.1)."
        ),
        rq_tags=["RQ1", "RQ2"],
        family="E4.1",
        status="runnable",
        script="ragas",
        base_args=["--ablation", "none"],
        params=[_LIMIT_PARAM],
        outputs_glob="experiments/ragas-*.md",
        gemini_cost_note="~3 metric Gemini calls/scenario on top of the pipeline run.",
        expected_runtime="~12–18 min for all 15.",
    ),
    Experiment(
        id="pairwise-judge",
        title="Pairwise LLM-judge with bias mitigation",
        summary="A-vs-B variant comparison with position-bias control.",
        description_plain=(
            "Compares two variants head-to-head by asking the model which "
            "answer is better, while controlling for the known tendency of "
            "models to favour whichever answer is shown first."
        ),
        description_technical=(
            "Pairwise Gemini judge over already-produced reports (reads the "
            "Day-2 result files, no pipeline re-run): 3 calls A/B + 3 calls "
            "B/A with an explicit 'ignore position and length' instruction, "
            "reference-based, aggregated by 6-vote majority. Reports win-rate "
            "and an order-inconsistency diagnostic for position bias (Zheng "
            "et al. 2024). Default pair: full system vs CoT-only baseline "
            "(E4.2)."
        ),
        rq_tags=["RQ1", "RQ2"],
        family="E4.2",
        status="runnable",
        script="pairwise",
        base_args=["--variant-a", "none", "--variant-b", "cot_only"],
        params=[_LIMIT_PARAM],
        outputs_glob="experiments/pairwise-*.md",
        gemini_cost_note="6 judge Gemini calls/scenario (no pipeline re-run).",
        expected_runtime="~6–10 min for all 15.",
    ),
    Experiment(
        id="bootstrap-cis",
        title="Bootstrap confidence intervals on score drift",
        summary="5-run memory evolution with 95% bootstrap CIs.",
        description_plain=(
            "Repeats the memory experiment several times and computes "
            "statistical confidence bounds, so we can say the upward/downward "
            "drift is real rather than random noise."
        ),
        description_technical=(
            "Runs memory-evolution 5× with varied seeds; computes 95% "
            "bootstrap CIs around #boosted / #demoted to test the drift "
            "direction against an equal-proportions null. Not yet implemented "
            "(E3.1)."
        ),
        rq_tags=["RQ3", "RO2"],
        family="E3.1",
        status="planned",
        gemini_cost_note="5× the memory-evolution cost.",
        expected_runtime="TBD (long).",
    ),
    Experiment(
        id="adversarial-poisoning",
        title="Adversarial memory poisoning",
        summary="Can reflection resist a misattributed incident?",
        description_plain=(
            "A stress test: feed the system a case crafted to push it toward "
            "the wrong past incident, and check that the self-critique step "
            "refuses to reward the irrelevant match — validating the safety "
            "of the learning loop."
        ),
        description_technical=(
            "Crafted scenario whose ground truth matches one incident while "
            "the reasoning agent is prompted to attribute it elsewhere; "
            "verifies reflection down-weights / refuses to boost the wrong "
            "incident. Validates the per-call clamp + reflection safeguard. "
            "Not yet implemented (E3.2)."
        ),
        rq_tags=["RQ1", "RQ3"],
        family="E3.2",
        status="planned",
        gemini_cost_note="A few Gemini calls.",
        expected_runtime="TBD.",
    ),
    Experiment(
        id="rank-lift",
        title="Did memory help? — retrieval rank lift",
        summary="Mean rank improvement of the expected incident over runs.",
        description_plain=(
            "Measures whether, after several runs, the correct past incident "
            "tends to appear higher in the retrieval list than it did at the "
            "start — direct evidence that the memory loop improves retrieval "
            "over time."
        ),
        description_technical=(
            "For each in-domain scenario, records the rank of the expected "
            "incident in run-1 vs run-N and reports mean rank improvement "
            "(MemoryAgentBench 'test-time learning'). Not yet implemented "
            "(E3.5)."
        ),
        rq_tags=["RQ3", "RO2"],
        family="E3.5",
        status="planned",
        gemini_cost_note="Same as memory-evolution.",
        expected_runtime="TBD.",
    ),
    Experiment(
        id="cost-vs-volume",
        title="Cost-vs-volume simulation (gating)",
        summary="Gated vs ungated Gemini-call count on a 1000-chunk stream.",
        description_plain=(
            "Simulates a realistic log stream where only a small fraction are "
            "real incidents, and counts how many expensive analyses the cheap "
            "classifier gate saves versus analysing every single chunk — the "
            "headline number for the efficiency claim. Needs no Gemini calls."
        ),
        description_technical=(
            "Simulates `total_chunks` at `incident_pct`% incident rate; counts "
            "Gemini invocations under gated (classifier-first) vs ungated (RCA "
            "on every chunk) policies and reports the reduction ratio plus a "
            "wall-time model (RQ4). Pure deterministic simulation, no Gemini "
            "(E6.3)."
        ),
        rq_tags=["RQ4"],
        family="E6.3",
        status="runnable",
        script="cost_vs_volume",
        base_args=[],
        params=[
            ParamSpec(
                name="total_chunks",
                label="Total log chunks",
                kind="int",
                cli_flag="--total-chunks",
                default=1000,
                minimum=1,
                maximum=1_000_000,
                help="Size of the simulated log stream.",
            ),
            ParamSpec(
                name="incident_pct",
                label="Incident rate (%)",
                kind="int",
                cli_flag="--incident-pct",
                default=5,
                minimum=0,
                maximum=100,
                help="Percentage of chunks that are real incidents (ERROR/FATAL).",
            ),
            ParamSpec(
                name="calls_per_rca",
                label="Gemini calls per RCA",
                kind="int",
                cli_flag="--calls-per-rca",
                default=4,
                minimum=1,
                maximum=10,
                help="LLM calls the multi-agent pipeline makes per investigation.",
            ),
        ],
        outputs_glob="experiments/cost-vs-volume-*.md",
        gemini=False,
        gemini_cost_note="No Gemini calls — deterministic and instant.",
        expected_runtime="Instant.",
    ),
    Experiment(
        id="classifier-metrics",
        title="Classifier precision / recall / F1",
        summary="ModernBERT gate metrics on the BGL test split.",
        description_plain=(
            "Shows how accurately the cheap first-stage classifier flags "
            "logs that deserve a full investigation, using precision, recall "
            "and F1 from its training evaluation — the evidence behind the "
            "gating claim."
        ),
        description_technical=(
            "Surfaces the fine-tuned ModernBERT classifier's P/R/F1 on the "
            "held-out BGL+Hadoop test split (read from `training_metadata.json` "
            "next to the model) as a markdown report (RQ4 / E7.1). Reads "
            "precomputed numbers — no training, no Gemini."
        ),
        rq_tags=["RQ4"],
        family="E7.1",
        status="runnable",
        script="classifier_metrics",
        base_args=[],
        params=[],
        outputs_glob="experiments/classifier-metrics-*.md",
        gemini=False,
        gemini_cost_note="No Gemini calls (precomputed at training time).",
        expected_runtime="Instant (precomputed).",
    ),
]


# Validate uniqueness at import time -- a duplicate id would silently
# shadow an experiment in the lookup below.
_seen: set[str] = set()
for _exp in EXPERIMENTS:
    if _exp.id in _seen:
        raise ValueError(f"duplicate experiment id in registry: {_exp.id}")
    _seen.add(_exp.id)

_BY_ID: dict[str, Experiment] = {e.id: e for e in EXPERIMENTS}


def list_experiments() -> list[Experiment]:
    """All experiments in registry (definition) order."""
    return list(EXPERIMENTS)


def get_experiment(experiment_id: str) -> Experiment | None:
    """Look up one experiment by id, or `None` if unknown."""
    return _BY_ID.get(experiment_id)
