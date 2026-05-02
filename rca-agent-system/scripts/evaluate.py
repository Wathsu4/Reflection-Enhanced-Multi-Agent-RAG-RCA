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

from rca_system.settings import settings  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "eval"
DEFAULT_DATASET = EVAL_DIR / "incidents.jsonl"


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


# -------------------- pipeline runner --------------------
# Lazy imports of the agent system so unit-test importing this module
# doesn't pull in the whole ADK stack (which is slow and requires a
# Gemini key).


async def _run_pipeline_for_scenario(scenario: Scenario) -> ScenarioResult:
    """Run the full root_agent pipeline on one scenario via ADK's
    in-process Runner. No HTTP server needed."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    from rca_system.agent import root_agent

    result = ScenarioResult(
        id=scenario.id,
        expected_incident_id=scenario.expected_incident_id,
    )

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="rca_system",
        user_id="evaluator",
    )
    runner = Runner(
        agent=root_agent,
        app_name="rca_system",
        session_service=session_service,
    )

    user_message = Content(
        role="user",
        parts=[Part(text=scenario.log_chunk)],
    )

    started = time.perf_counter()
    events_dict: list[dict] = []
    final_output: str | None = None
    retrieval_payload: Any = None
    try:
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_message,
        ):
            # ADK events expose `model_dump_json` on the pydantic model.
            try:
                events_dict.append(json.loads(event.model_dump_json()))
            except Exception:
                # Best-effort: don't let serialization break the eval.
                events_dict.append({"author": getattr(event, "author", "?")})

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

    if final_output:
        result.final_markdown = final_output
        result.extracted_root_cause = extract_root_cause(final_output)
        result.keyword_score = round(
            keyword_score(result.extracted_root_cause, scenario.ground_truth_keywords),
            3,
        )
        result.keyword_verdict = keyword_verdict(result.keyword_score)

    # Pull retrieval signals (top similarity + whether the expected
    # incident appeared) from the retrieval_output JSON. Retrieval
    # agents emit JSON in their text but the state_delta should hold
    # the same payload.
    if retrieval_payload:
        try:
            data = (
                retrieval_payload
                if isinstance(retrieval_payload, dict)
                else json.loads(str(retrieval_payload))
            )
            hits = data.get("hits") or []
            if hits:
                result.top_retrieval_similarity = float(hits[0].get("similarity", 0.0))
                if scenario.expected_incident_id is not None:
                    found = any(
                        h.get("incident_id") == scenario.expected_incident_id
                        for h in hits
                    )
                    result.expected_incident_retrieved = found
                else:
                    # OOD scenario -- success is "we didn't have a strong
                    # match"; record None so aggregation can skip it.
                    result.expected_incident_retrieved = None
        except Exception:
            pass

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

    return {
        "n": n,
        "n_in_domain": len(in_domain),
        "n_ood": n - len(in_domain),
        "keyword_verdict_counts": verdict_counts,
        "keyword_accuracy_exact_or_partial": round(
            (verdict_counts["exact"] + verdict_counts["partial"]) / n, 3
        ),
        "expected_incident_retrieval_recall": (
            round(expected_hits / len(in_domain), 3) if in_domain else None
        ),
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
        "mean_top_retrieval_similarity": (
            round(statistics.mean(sims), 3) if sims else None
        ),
        "llm_judge_verdict_counts": judge_counts or None,
    }


def render_markdown_report(
    results: list[ScenarioResult], summary: dict[str, Any]
) -> str:
    lines: list[str] = []
    lines.append("# RCA pipeline evaluation\n")
    lines.append(f"- Scenarios: **{summary['n']}** "
                 f"({summary['n_in_domain']} in-domain, "
                 f"{summary['n_ood']} OOD)")
    if summary.get("mean_latency_s") is not None:
        lines.append(
            f"- Mean latency: **{summary['mean_latency_s']}s** "
            f"(p95 ≈ {summary['p95_latency_s']}s)"
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
    vc = summary["keyword_verdict_counts"]
    lines.append(
        f"- Keyword verdicts: exact={vc['exact']}, "
        f"partial={vc['partial']}, miss={vc['miss']} "
        f"(exact-or-partial = **{summary['keyword_accuracy_exact_or_partial']}**)"
    )
    if summary.get("llm_judge_verdict_counts"):
        jc = summary["llm_judge_verdict_counts"]
        lines.append(f"- LLM-judge verdicts: {jc}")

    lines.append("\n## Per-scenario\n")
    lines.append(
        "| id | verdict | kw score | top sim | "
        "expected hit | latency (s) | judge |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.id} | {r.keyword_verdict} | "
            f"{r.keyword_score:.2f} | "
            f"{r.top_retrieval_similarity if r.top_retrieval_similarity is not None else '—'} | "
            f"{('hit' if r.expected_incident_retrieved else 'miss') if r.expected_incident_id else 'OOD'} | "
            f"{r.latency_s} | {r.llm_judge_verdict or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


# -------------------- entry point --------------------


async def amain(args: argparse.Namespace) -> int:
    scenarios = load_scenarios(args.dataset)
    if args.limit > 0:
        scenarios = scenarios[: args.limit]
    print(f"Loaded {len(scenarios)} scenarios from {args.dataset}", file=sys.stderr)

    EVAL_DIR.mkdir(exist_ok=True)
    results: list[ScenarioResult] = []
    for i, sc in enumerate(scenarios, 1):
        print(f"  [{i}/{len(scenarios)}] {sc.id} …", file=sys.stderr, flush=True)
        r = await _run_pipeline_for_scenario(sc)
        if args.llm_judge and r.extracted_root_cause and r.error is None:
            try:
                r.llm_judge_verdict = await _llm_judge(sc, r.extracted_root_cause)
            except Exception as exc:
                r.llm_judge_verdict = f"error: {type(exc).__name__}"
        results.append(r)

    summary = summarize(results)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = EVAL_DIR / f"results-{timestamp}.json"
    md_path = EVAL_DIR / f"results-{timestamp}.md"

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
    args = parser.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
