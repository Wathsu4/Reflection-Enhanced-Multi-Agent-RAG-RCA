"""Evaluate the RCA pipeline against `eval/incidents.jsonl`.

For each scenario in the dataset:
  1. Send the log chunk through the four-stage pipeline (using ADK's
     in-process Runner -- no HTTP server needed for evaluation).
  2. Extract the final markdown's `## Root cause` section.
  3. Score the hypothesis against the ground truth.

Scoring options (composable):
  * `--keywords`  (default): does the hypothesis contain a sufficient
    fraction of the curated keyword list? Cheap, deterministic.
  * `--llm-judge`: ask Gemini "is hypothesis H consistent with ground
    truth G?" and aggregate the verdicts. More robust but slow + costs
    quota; flaky single-shot, so we ask 3 times and take majority.

Side metrics: pipeline latency (s), top-hit retrieval similarity, and
whether the expected incident id appeared in the retrieval output (when
the dataset declared one).

Outputs:
  * `eval/results-{timestamp}.json` -- full per-scenario record
  * `eval/results-{timestamp}.md`   -- thesis-ready summary table

Usage:
    uv run python scripts/evaluate.py                # keyword scoring only
    uv run python scripts/evaluate.py --llm-judge    # adds Gemini judge
    uv run python scripts/evaluate.py --limit 3      # smoke test, 3 cases
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.ablations import ABLATIONS, DETERMINISTIC_ABLATIONS, build_root_agent  # noqa: E402
from rca_system.settings import settings  # noqa: E402

# ADK's google-genai auth reads GOOGLE_API_KEY from the process environment,
# but pydantic-settings only loads it into `settings` (it never exports it).
# When this script runs the in-process ADK Runner -- via CLI or the eval
# console subprocess -- bridge the key into os.environ so the pipeline can
# authenticate. (The HTTP server gets this for free from ADK's own .env load.)
import os  # noqa: E402

if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
if not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = settings.google_genai_use_vertexai

EVAL_DIR = PROJECT_ROOT / "eval"
# Ablation / baseline runs land here so they never clobber the demo-ready
# `eval/results-*.md` reports (see How-To-Evaluate/PLAN.md decision log).
EXPERIMENTS_DIR = EVAL_DIR / "experiments"
DEFAULT_DATASET = EVAL_DIR / "incidents.jsonl"


# -------------------- progress (for the eval UI) --------------------


def _emit_progress(enabled: bool, **fields: Any) -> None:
    """Emit one compact JSON lifecycle line to stdout when `--progress-json`
    is set. The eval-console JobManager tails these lines to drive the live
    progress UI. Human-readable logging stays on stderr regardless.

    Each line has an `event` key, one of: run_start, scenario_start,
    scenario_done, run_done.
    """
    if not enabled:
        return
    print(json.dumps(fields, default=str), flush=True)


# -------------------- dataset I/O --------------------


@dataclass
class Scenario:
    id: str
    log_chunk: str
    ground_truth_root_cause: str
    ground_truth_keywords: list[str]
    expected_incident_id: str | None


def load_scenarios(path: Path) -> list[Scenario]:
    """One JSON object per line; missing optional fields default safely."""
    out: list[Scenario] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        out.append(
            Scenario(
                id=str(d["id"]),
                log_chunk=str(d["log_chunk"]),
                ground_truth_root_cause=str(d["ground_truth_root_cause"]),
                ground_truth_keywords=[str(k) for k in d.get("ground_truth_keywords", [])],
                expected_incident_id=d.get("expected_incident_id"),
            )
        )
    return out


# -------------------- scoring helpers --------------------


_ROOT_CAUSE_RE = re.compile(
    r"##\s*Root\s*cause\s*[:\-]?\s*\r?\n+([^\n#]+)", re.IGNORECASE
)


def extract_root_cause(markdown: str) -> str:
    """Mirror of the frontend extractor in `extract-root-cause.ts`.

    Pulls the first paragraph under the `## Root cause` heading.
    """
    if not markdown:
        return ""
    m = _ROOT_CAUSE_RE.search(markdown)
    return m.group(1).strip() if m else ""


def keyword_score(text: str, keywords: list[str]) -> float:
    """Fraction of `keywords` present in `text` (case-insensitive,
    word-substring match). Returns 0.0 if `keywords` is empty.

    This is a deliberately simple metric: it cannot reward correct
    paraphrases, but it punishes hallucinated root causes that miss
    the specific terms a domain expert would expect.
    """
    if not keywords:
        return 0.0
    t = text.lower()
    hits = sum(1 for k in keywords if k.lower() in t)
    return hits / len(keywords)


def keyword_verdict(score: float) -> str:
    """Bucket a fractional score into a thesis-friendly label."""
    if score >= 0.66:
        return "exact"
    if score >= 0.33:
        return "partial"
    return "miss"


# -------------------- per-scenario record --------------------


@dataclass
class ScenarioResult:
    id: str
    expected_incident_id: str | None
    final_markdown: str = ""
    extracted_root_cause: str = ""
    keyword_score: float = 0.0
    keyword_verdict: str = "miss"
    expected_incident_retrieved: bool | None = None
    top_retrieval_similarity: float | None = None
    latency_s: float = 0.0
    llm_judge_verdict: str | None = None
    error: str | None = None
    raw_events: list[dict] = field(default_factory=list)
    # --- plumbing-pass additions (PLAN.md Day 1) ---
    # Which pipeline variant produced this result.
    ablation: str = "none"
    # Per-stage wall-clock latency, keyed by agent author name (E6.1).
    stage_latency_s: dict[str, float] = field(default_factory=dict)
    # Gemini token usage. `stage_tokens` is keyed by author; the scalar
    # fields are the per-scenario totals across all stages (E6.2).
    stage_tokens: dict[str, int] = field(default_factory=dict)
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    # Retrieval IR signals (E4.4). `retrieved_ids` is the ranked hit list
    # in the order the retrieval tool returned it; `expected_incident_rank`
    # is the 1-based position of the expected incident (None if absent or
    # the scenario is OOD).
    retrieved_ids: list[str] = field(default_factory=list)
    expected_incident_rank: int | None = None


# -------------------- pipeline runner --------------------
# Lazy imports of the agent system so unit-test importing this module
# doesn't pull in the whole ADK stack (which is slow and requires a
# Gemini key).


def _apply_retrieval_signals(
    result: ScenarioResult, scenario: Scenario, retrieval_payload: Any
) -> None:
    """Populate the retrieval-derived metrics on `result` from a
    `retrieval_output` payload (the JSON the retrieval tool produced).

    Sets top similarity, the ranked hit-id list, whether the expected
    incident was retrieved, and its 1-based rank (E4.4). Shared by the
    ADK path and the deterministic `retrieval_only` baseline.
    """
    if not retrieval_payload:
        return
    try:
        data = (
            retrieval_payload
            if isinstance(retrieval_payload, dict)
            else json.loads(str(retrieval_payload))
        )
        hits = data.get("hits") or []
        if not hits:
            return
        result.top_retrieval_similarity = float(hits[0].get("similarity", 0.0))
        result.retrieved_ids = [str(h.get("incident_id", "")) for h in hits]
        if scenario.expected_incident_id is not None:
            rank: int | None = None
            for i, h in enumerate(hits, 1):
                if h.get("incident_id") == scenario.expected_incident_id:
                    rank = i
                    break
            result.expected_incident_rank = rank
            result.expected_incident_retrieved = rank is not None
        else:
            # OOD scenario -- success is "we didn't have a strong match";
            # record None so aggregation can skip it.
            result.expected_incident_retrieved = None
    except Exception:
        pass


def _score_final_output(result: ScenarioResult, scenario: Scenario) -> None:
    """Run keyword scoring on whatever final markdown `result` holds."""
    if not result.final_markdown:
        return
    result.extracted_root_cause = extract_root_cause(result.final_markdown)
    result.keyword_score = round(
        keyword_score(result.extracted_root_cause, scenario.ground_truth_keywords),
        3,
    )
    result.keyword_verdict = keyword_verdict(result.keyword_score)


def _run_retrieval_only(scenario: Scenario, k: int = 5) -> ScenarioResult:
    """Deterministic `retrieval_only` baseline (E2.1): no LLM call.

    Retrieve the top-k incidents (with the production
    `similarity * success_score` re-ranking) and synthesise a minimal
    report whose `## Root cause` is the top hit's stored root cause. This
    is the zero-hallucination floor that any LLM variant must beat.
    """
    from rca_system.tools.retrieve_incidents import retrieve_incidents

    result = ScenarioResult(
        id=scenario.id,
        expected_incident_id=scenario.expected_incident_id,
        ablation="retrieval_only",
    )
    started = time.perf_counter()
    try:
        payload = retrieve_incidents(query=scenario.log_chunk, k=k)
        hits = payload.get("hits") or []
        if hits:
            top = hits[0]
            result.final_markdown = (
                "## Root cause\n"
                f"{top.get('root_cause', '').strip()}\n\n"
                "## Suggested actions\n"
                f"- {top.get('resolution', '').strip() or 'See retrieved incident.'}\n\n"
                "## Confidence & caveats\n"
                "Retrieval-only baseline: returns the closest past incident "
                "verbatim, with no LLM reasoning.\n\n"
                "## Memory updates\n"
                "No memory changes applied.\n"
            )
        _apply_retrieval_signals(result, scenario, payload)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        result.latency_s = round(time.perf_counter() - started, 3)

    _score_final_output(result, scenario)
    return result


async def _run_pipeline_for_scenario(
    scenario: Scenario, ablation: str = "none"
) -> ScenarioResult:
    """Run a pipeline variant on one scenario via ADK's in-process Runner.

    `ablation` selects which wiring to run (see `rca_system.ablations`).
    The deterministic `retrieval_only` baseline is dispatched to
    `_run_retrieval_only` and performs no LLM call.
    """
    if ablation in DETERMINISTIC_ABLATIONS:
        return _run_retrieval_only(scenario)

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    agent = build_root_agent(ablation)

    result = ScenarioResult(
        id=scenario.id,
        expected_incident_id=scenario.expected_incident_id,
        ablation=ablation,
    )

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="rca_system",
        user_id="evaluator",
    )
    runner = Runner(
        agent=agent,
        app_name="rca_system",
        session_service=session_service,
    )

    user_message = Content(
        role="user",
        parts=[Part(text=scenario.log_chunk)],
    )

    started = time.perf_counter()
    # Per-stage timing: attribute the wall time leading up to each event
    # to that event's author (stages run sequentially, so this cleanly
    # partitions total latency across agents). Token usage is summed from
    # each event's `usage_metadata` (E6.1 / E6.2).
    prev_ts = started
    stage_latency: dict[str, float] = {}
    stage_tokens: dict[str, int] = {}
    events_dict: list[dict] = []
    final_output: str | None = None
    retrieval_payload: Any = None
    try:
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_message,
        ):
            now = time.perf_counter()
            author = getattr(event, "author", None) or "unknown"
            stage_latency[author] = round(
                stage_latency.get(author, 0.0) + (now - prev_ts), 3
            )
            prev_ts = now

            usage = getattr(event, "usage_metadata", None)
            if usage is not None:
                prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
                cand = int(getattr(usage, "candidates_token_count", 0) or 0)
                total = int(
                    getattr(usage, "total_token_count", 0) or (prompt + cand)
                )
                result.prompt_tokens += prompt
                result.output_tokens += cand
                result.total_tokens += total
                stage_tokens[author] = stage_tokens.get(author, 0) + total

            # ADK events expose `model_dump_json` on the pydantic model.
            try:
                events_dict.append(json.loads(event.model_dump_json()))
            except Exception:
                # Best-effort: don't let serialization break the eval.
                events_dict.append({"author": author})

            actions = getattr(event, "actions", None)
            state_delta = getattr(actions, "state_delta", None) or {}
            if "final_output" in state_delta:
                v = state_delta["final_output"]
                if isinstance(v, str) and v.strip():
                    final_output = v
            if "retrieval_output" in state_delta:
                retrieval_payload = state_delta["retrieval_output"]
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        result.latency_s = round(time.perf_counter() - started, 3)
        result.raw_events = events_dict
        result.stage_latency_s = stage_latency
        result.stage_tokens = stage_tokens

    if final_output:
        result.final_markdown = final_output
        _score_final_output(result, scenario)

    # Pull retrieval signals from the retrieval_output JSON. (Absent for
    # no_rag / cot_only, which skip the retrieval stage entirely.)
    _apply_retrieval_signals(result, scenario, retrieval_payload)

    return result


async def _llm_judge(
    scenario: Scenario, hypothesis: str, n: int = 3
) -> str:
    """Ask Gemini to judge `yes`/`partial`/`no` against the ground truth.

    Returns the majority vote across `n` calls. Each call is
    independent and uses a fresh agent (no state leak).
    """
    if not hypothesis.strip():
        return "no"

    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=settings.google_api_key)

    prompt = (
        "You are a strict reviewer of root-cause analysis hypotheses.\n\n"
        f"Ground truth root cause:\n{scenario.ground_truth_root_cause}\n\n"
        f"Hypothesis under review:\n{hypothesis}\n\n"
        "Answer with ONE word, exactly one of: yes / partial / no.\n"
        "  'yes' if the hypothesis correctly identifies the root cause.\n"
        "  'partial' if it identifies symptoms or a related but not\n"
        "      identical cause.\n"
        "  'no' otherwise."
    )

    votes: list[str] = []
    for _ in range(n):
        try:
            resp = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.0),
            )
            txt = (resp.text or "").strip().lower().split()[0]
            votes.append(txt if txt in {"yes", "partial", "no"} else "no")
        except Exception:
            votes.append("error")
    # Majority vote; ties default to the most conservative label (no).
    counts = {v: votes.count(v) for v in {"yes", "partial", "no", "error"}}
    if counts.get("error", 0) >= n // 2 + 1:
        return "error"
    counts.pop("error", None)
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else "no"


# -------------------- main aggregation --------------------


def _retrieval_ir_metrics(
    in_domain: list[ScenarioResult], k: int = 5
) -> dict[str, Any]:
    """Standard IR triad over the in-domain scenarios (E4.4).

    Each scenario has exactly one relevant incident (`expected_incident_id`),
    so binary-relevance nDCG and reciprocal rank are well-defined.

      * Recall@k -- fraction of scenarios where the expected incident is in
        the top-k hits.
      * MRR      -- mean of 1/rank (0 when the expected incident is absent).
      * nDCG@k   -- mean of 1/log2(rank+1) (IDCG is 1.0 for a single
        relevant item, so DCG == nDCG here).

    Only scenarios that actually produced a retrieval list are counted.
    """
    import math

    scored = [r for r in in_domain if r.retrieved_ids]
    if not scored:
        return {
            "n_scored": 0,
            "recall_at_k": None,
            "mrr": None,
            "ndcg_at_k": None,
            "k": k,
        }

    recalls: list[float] = []
    rr: list[float] = []
    ndcg: list[float] = []
    for r in scored:
        rank = r.expected_incident_rank
        in_top_k = rank is not None and rank <= k
        recalls.append(1.0 if in_top_k else 0.0)
        rr.append(1.0 / rank if rank is not None else 0.0)
        ndcg.append(1.0 / math.log2(rank + 1) if in_top_k else 0.0)

    return {
        "n_scored": len(scored),
        "recall_at_k": round(statistics.mean(recalls), 3),
        "mrr": round(statistics.mean(rr), 3),
        "ndcg_at_k": round(statistics.mean(ndcg), 3),
        "k": k,
    }


def _aggregate_stage_metric(
    results: list[ScenarioResult], attr: str
) -> dict[str, float]:
    """Mean of a per-author dict metric (`stage_latency_s` or
    `stage_tokens`) across all results that recorded it."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in results:
        for author, value in (getattr(r, attr) or {}).items():
            totals[author] = totals.get(author, 0.0) + float(value)
            counts[author] = counts.get(author, 0) + 1
    return {
        author: round(totals[author] / counts[author], 3)
        for author in totals
    }


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    """Compute thesis-friendly aggregate metrics from per-scenario data."""
    n = len(results)
    if n == 0:
        return {"n": 0}

    verdict_counts = {
        v: sum(1 for r in results if r.keyword_verdict == v)
        for v in ("exact", "partial", "miss")
    }

    latencies = [r.latency_s for r in results if r.latency_s > 0]
    sims = [
        r.top_retrieval_similarity
        for r in results
        if r.top_retrieval_similarity is not None
    ]

    in_domain = [r for r in results if r.expected_incident_id is not None]
    expected_hits = sum(
        1 for r in in_domain if r.expected_incident_retrieved is True
    )

    judge_counts: dict[str, int] = {}
    for r in results:
        if r.llm_judge_verdict is not None:
            judge_counts[r.llm_judge_verdict] = (
                judge_counts.get(r.llm_judge_verdict, 0) + 1
            )

    token_totals = [r.total_tokens for r in results if r.total_tokens > 0]
    ablations = {r.ablation for r in results}

    return {
        "n": n,
        "ablation": next(iter(ablations)) if len(ablations) == 1 else sorted(ablations),
        "n_in_domain": len(in_domain),
        "n_ood": n - len(in_domain),
        "keyword_verdict_counts": verdict_counts,
        "keyword_accuracy_exact_or_partial": round(
            (verdict_counts["exact"] + verdict_counts["partial"]) / n, 3
        ),
        "expected_incident_retrieval_recall": (
            round(expected_hits / len(in_domain), 3) if in_domain else None
        ),
        "retrieval_ir": _retrieval_ir_metrics(in_domain),
        "mean_latency_s": (
            round(statistics.mean(latencies), 3) if latencies else None
        ),
        "p95_latency_s": (
            round(
                statistics.quantiles(latencies, n=20)[-1]
                if len(latencies) >= 20
                else max(latencies),
                3,
            )
            if latencies
            else None
        ),
        "mean_stage_latency_s": _aggregate_stage_metric(results, "stage_latency_s")
        or None,
        "mean_top_retrieval_similarity": (
            round(statistics.mean(sims), 3) if sims else None
        ),
        "mean_total_tokens": (
            round(statistics.mean(token_totals), 1) if token_totals else None
        ),
        "mean_stage_tokens": _aggregate_stage_metric(results, "stage_tokens")
        or None,
        "llm_judge_verdict_counts": judge_counts or None,
    }


def render_markdown_report(
    results: list[ScenarioResult], summary: dict[str, Any]
) -> str:
    lines: list[str] = []
    lines.append("# RCA pipeline evaluation\n")
    lines.append(f"- Variant (ablation): **{summary.get('ablation', 'none')}**")
    lines.append(f"- Scenarios: **{summary['n']}** "
                 f"({summary['n_in_domain']} in-domain, "
                 f"{summary['n_ood']} OOD)")
    if summary.get("mean_latency_s") is not None:
        lines.append(
            f"- Mean latency: **{summary['mean_latency_s']}s** "
            f"(p95 ≈ {summary['p95_latency_s']}s)"
        )
    if summary.get("mean_total_tokens") is not None:
        lines.append(
            f"- Mean Gemini tokens / scenario: **{summary['mean_total_tokens']}**"
        )
    if summary.get("mean_top_retrieval_similarity") is not None:
        lines.append(
            f"- Mean top retrieval similarity: "
            f"**{summary['mean_top_retrieval_similarity']}**"
        )
    if summary.get("expected_incident_retrieval_recall") is not None:
        lines.append(
            "- Expected-incident retrieval recall (in-domain only): "
            f"**{summary['expected_incident_retrieval_recall']}**"
        )
    ir = summary.get("retrieval_ir") or {}
    if ir.get("recall_at_k") is not None:
        lines.append(
            f"- Retrieval IR (in-domain, n={ir['n_scored']}, k={ir['k']}): "
            f"Recall@k=**{ir['recall_at_k']}**, MRR=**{ir['mrr']}**, "
            f"nDCG@k=**{ir['ndcg_at_k']}**"
        )
    vc = summary["keyword_verdict_counts"]
    lines.append(
        f"- Keyword verdicts: exact={vc['exact']}, "
        f"partial={vc['partial']}, miss={vc['miss']} "
        f"(exact-or-partial = **{summary['keyword_accuracy_exact_or_partial']}**)"
    )
    if summary.get("llm_judge_verdict_counts"):
        jc = summary["llm_judge_verdict_counts"]
        lines.append(f"- LLM-judge verdicts: {jc}")

    stage_lat = summary.get("mean_stage_latency_s")
    stage_tok = summary.get("mean_stage_tokens")
    if stage_lat or stage_tok:
        lines.append("\n## Per-stage breakdown (mean across scenarios)\n")
        lines.append("| stage | latency (s) | tokens |")
        lines.append("|---|---|---|")
        authors = sorted(set(stage_lat or {}) | set(stage_tok or {}))
        for a in authors:
            lat = (stage_lat or {}).get(a, "—")
            tok = (stage_tok or {}).get(a, "—")
            lines.append(f"| {a} | {lat} | {tok} |")

    lines.append("\n## Per-scenario\n")
    lines.append(
        "| id | verdict | kw score | top sim | rank | "
        "expected hit | latency (s) | tokens | judge |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.id} | {r.keyword_verdict} | "
            f"{r.keyword_score:.2f} | "
            f"{r.top_retrieval_similarity if r.top_retrieval_similarity is not None else '—'} | "
            f"{r.expected_incident_rank if r.expected_incident_rank is not None else '—'} | "
            f"{('hit' if r.expected_incident_retrieved else 'miss') if r.expected_incident_id else 'OOD'} | "
            f"{r.latency_s} | {r.total_tokens or '—'} | {r.llm_judge_verdict or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


# -------------------- entry point --------------------


async def amain(args: argparse.Namespace) -> int:
    scenarios = load_scenarios(args.dataset)
    if args.limit > 0:
        scenarios = scenarios[: args.limit]
    print(f"Loaded {len(scenarios)} scenarios from {args.dataset}", file=sys.stderr)

    ablation = args.ablation
    progress = args.progress_json
    print(f"Pipeline variant: {ablation}", file=sys.stderr)
    n = len(scenarios)
    _emit_progress(
        progress,
        event="run_start",
        kind="pipeline",
        total=n,
        ablation=ablation,
        llm_judge=bool(args.llm_judge),
    )

    results: list[ScenarioResult] = []
    for i, sc in enumerate(scenarios, 1):
        print(f"  [{i}/{n}] {sc.id} …", file=sys.stderr, flush=True)
        _emit_progress(progress, event="scenario_start", i=i, n=n, id=sc.id)
        r = await _run_pipeline_for_scenario(sc, ablation=ablation)
        if args.llm_judge and r.extracted_root_cause and r.error is None:
            try:
                r.llm_judge_verdict = await _llm_judge(sc, r.extracted_root_cause)
            except Exception as exc:
                r.llm_judge_verdict = f"error: {type(exc).__name__}"
        results.append(r)
        _emit_progress(
            progress,
            event="scenario_done",
            i=i,
            n=n,
            id=sc.id,
            verdict=r.keyword_verdict,
            keyword_score=r.keyword_score,
            latency_s=r.latency_s,
            error=r.error,
        )

    summary = summarize(results)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    # Non-default variants are experiments -- keep them out of the
    # demo-ready eval/ reports and tag the filename with the variant.
    if ablation == "none":
        out_dir = EVAL_DIR
        stem = f"results-{timestamp}"
    else:
        out_dir = EXPERIMENTS_DIR
        stem = f"results-{ablation}-{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"

    json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "results": [asdict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(results, summary), encoding="utf-8")

    print(f"\nWrote {json_path} and {md_path}", file=sys.stderr)
    _emit_progress(
        progress,
        event="run_done",
        summary=summary,
        json_path=str(json_path),
        md_path=str(md_path),
    )
    # When emitting progress JSONL, skip the pretty multi-line dump so the
    # consumer sees only single-line JSON events on stdout.
    if not progress:
        print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="JSONL file of scenarios (default: eval/incidents.jsonl).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run only the first N scenarios (0 = all). Useful for smoke tests.",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help=(
            "Also score each hypothesis with a Gemini-as-judge call "
            "(slower, costs quota). Verdicts are majority-vote across 3 calls."
        ),
    )
    parser.add_argument(
        "--ablation",
        choices=ABLATIONS,
        default="none",
        help=(
            "Pipeline variant to evaluate (default: none = full system). "
            "Non-default variants write to eval/experiments/ so they don't "
            "clobber the demo-ready reports. See rca_system/ablations.py."
        ),
    )
    parser.add_argument(
        "--progress-json",
        action="store_true",
        help=(
            "Emit machine-readable JSONL lifecycle events to stdout "
            "(run_start / scenario_start / scenario_done / run_done) for the "
            "evaluation console to render live progress. Suppresses the "
            "trailing pretty summary dump."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
