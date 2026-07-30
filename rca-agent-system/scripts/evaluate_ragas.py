"""RAG-triad evaluation (RAGAS-style) for the RCA pipeline (E4.1).

Three reference-free quality metrics, re-implemented locally (no langchain
dependency) so they integrate with our Gemini-call style and the eval
console:

  * faithfulness        -- fraction of atomic claims in the final report
                           that are supported by the retrieved incident
                           context. Catches hallucination. (Gemini)
  * answer_relevancy    -- mean cosine similarity between the original log
                           chunk and N questions Gemini back-generates from
                           the report. Catches off-topic / padded answers.
                           (Gemini + local embeddings)
  * context_precision   -- rank-aware average precision of the retrieved
                           incidents w.r.t. those the reasoning agent
                           actually cited. Catches noisy retrieval.
                           (deterministic -- no Gemini)

The metric functions take injected `ask` / `embed` callables so they are
unit-testable without Gemini or a model download.

Writes a markdown report to `eval/experiments/ragas-{ablation}-{ts}.md`.

Usage:
    uv run python scripts/evaluate_ragas.py
    uv run python scripts/evaluate_ragas.py --ablation none --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import time
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.ablations import ABLATIONS, DETERMINISTIC_ABLATIONS  # noqa: E402
from scripts._eval_common import (  # noqa: E402
    DEFAULT_DATASET,
    EXPERIMENTS_DIR,
    AskFn,
    bridge_genai_env,
    emit_progress,
    make_ask,
    run_with_retry,
    state_delta,
    stream_pipeline_events,
    write_report,
)

# Reuse the dataset loader + root-cause extractor from the main eval script.
from scripts.evaluate import Scenario, load_scenarios  # noqa: E402

bridge_genai_env()

# Async callable shape for dependency injection in tests.
EmbedFn = Callable[[list[str]], list[list[float]]]


# -------------------- small parsing/maths helpers --------------------


def _strip_fences(text: str) -> str:
    """Drop a leading/trailing ```json ... ``` fence if present."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_json(text: str) -> Any:
    try:
        return json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# -------------------- the three metrics --------------------


def context_precision(retrieved_ids: list[str], used_ids: list[str]) -> float | None:
    """Rank-aware average precision of the retrieved list w.r.t. the
    incidents the reasoning agent cited (`used_ids` are the proxy for
    "relevant").

    Returns None when nothing was retrieved (e.g. no_rag). When incidents
    were retrieved but none cited, precision is 0.0 (pure noise).
    """
    if not retrieved_ids:
        return None
    used = set(used_ids)
    relevant_total = sum(1 for r in retrieved_ids if r in used)
    if relevant_total == 0:
        return 0.0
    hits = 0
    score = 0.0
    for i, rid in enumerate(retrieved_ids, 1):
        if rid in used:
            hits += 1
            score += hits / i
    return round(score / relevant_total, 4)


async def faithfulness(
    report: str, contexts: list[str], *, ask: AskFn
) -> tuple[float | None, int, int]:
    """Fraction of atomic claims in `report` supported by `contexts`.

    Two Gemini calls: extract claims, then judge support. Returns
    (score|None, supported, total). None when there is no retrieved
    context to ground against, or no claims could be extracted.
    """
    if not report.strip() or not contexts:
        return None, 0, 0

    claims_raw = await ask(
        "Extract the distinct factual claims made in the following "
        "root-cause-analysis report as a JSON array of short strings "
        "(one claim each, no nesting). Output ONLY the JSON array.\n\n"
        f"REPORT:\n{report}"
    )
    claims = _parse_json(claims_raw)
    if not isinstance(claims, list) or not claims:
        return None, 0, 0
    claims = [str(c) for c in claims][:12]

    context_block = "\n\n".join(f"- {c}" for c in contexts)
    verdict_raw = await ask(
        "You are checking whether each claim is supported by the provided "
        "context (retrieved past incidents). For each claim, answer true if "
        "the context supports it, false otherwise. Output ONLY a JSON array "
        "of booleans, same length and order as the claims.\n\n"
        f"CONTEXT:\n{context_block}\n\n"
        f"CLAIMS (JSON):\n{json.dumps(claims)}"
    )
    verdicts = _parse_json(verdict_raw)
    if not isinstance(verdicts, list) or not verdicts:
        return None, 0, len(claims)
    supported = sum(1 for v in verdicts[: len(claims)] if v is True)
    total = len(claims)
    return round(supported / total, 4), supported, total


async def answer_relevancy(
    report: str,
    log_chunk: str,
    *,
    ask: AskFn,
    embed: EmbedFn,
    n_questions: int = 3,
) -> float | None:
    """Mean cosine similarity between the original log chunk and N questions
    back-generated from the report. None if no report / no questions."""
    if not report.strip():
        return None
    q_raw = await ask(
        f"Read this root-cause-analysis report and write {n_questions} "
        "concise questions that the report directly answers. Output ONLY a "
        "JSON array of question strings.\n\n"
        f"REPORT:\n{report}"
    )
    questions = _parse_json(q_raw)
    if not isinstance(questions, list) or not questions:
        return None
    questions = [str(q) for q in questions][:n_questions]

    vecs = embed([log_chunk, *questions])
    chunk_vec, q_vecs = vecs[0], vecs[1:]
    if not q_vecs:
        return None
    sims = [_cosine(chunk_vec, qv) for qv in q_vecs]
    return round(sum(sims) / len(sims), 4)


# -------------------- pipeline runner (captures retrieval + reasoning) --------------------


@dataclass
class RagasResult:
    id: str
    ablation: str
    faithfulness: float | None = None
    faithful_supported: int = 0
    faithful_total: int = 0
    answer_relevancy: float | None = None
    context_precision: float | None = None
    n_retrieved: int = 0
    n_used: int = 0
    error: str | None = None


async def _run_pipeline_capture(scenario: Scenario, ablation: str) -> dict[str, Any]:
    """Run the pipeline variant and capture the final report plus the
    retrieval and reasoning JSON payloads from session state."""
    final_output: str | None = None
    retrieval_payload: Any = None
    reasoning_payload: Any = None
    error: str | None = None
    try:
        async for event in stream_pipeline_events(
            scenario.log_chunk, ablation=ablation, user_id="ragas"
        ):
            sd = state_delta(event)
            if isinstance(sd.get("final_output"), str) and sd["final_output"].strip():
                final_output = sd["final_output"]
            if "retrieval_output" in sd:
                retrieval_payload = sd["retrieval_output"]
            if "reasoning_output" in sd:
                reasoning_payload = sd["reasoning_output"]
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    def _as_dict(v: Any) -> dict[str, Any]:
        if isinstance(v, dict):
            return v
        parsed = _parse_json(str(v)) if v else None
        return parsed if isinstance(parsed, dict) else {}

    return {
        "final_output": final_output or "",
        "retrieval": _as_dict(retrieval_payload),
        "reasoning": _as_dict(reasoning_payload),
        "error": error,
    }


# -------------------- embed (production impl) --------------------


def _make_embed() -> EmbedFn:
    from chromadb.utils import embedding_functions

    ef = embedding_functions.DefaultEmbeddingFunction()

    def embed(texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in ef(texts)]

    return embed


# -------------------- per-scenario orchestration --------------------


async def score_scenario(
    scenario: Scenario, ablation: str, *, ask: AskFn, embed: EmbedFn
) -> RagasResult:
    res = RagasResult(id=scenario.id, ablation=ablation)
    captured = await _run_pipeline_capture(scenario, ablation)
    if captured["error"]:
        res.error = captured["error"]
        return res

    report = captured["final_output"] or ""
    hits = captured["retrieval"].get("hits") or []
    retrieved_ids = [str(h.get("incident_id", "")) for h in hits]
    used_ids = [str(x) for x in (captured["reasoning"].get("used_incident_ids") or [])]
    res.n_retrieved = len(retrieved_ids)
    res.n_used = len(used_ids)

    # Build the grounding context from retrieved incident bodies.
    contexts = [
        f"{h.get('title', '')}: {h.get('root_cause', '')} {h.get('resolution', '')}".strip()
        for h in hits
    ]

    res.context_precision = context_precision(retrieved_ids, used_ids)
    try:
        res.faithfulness, res.faithful_supported, res.faithful_total = await faithfulness(
            report, contexts, ask=ask
        )
    except Exception as exc:  # noqa: BLE001
        res.error = f"faithfulness: {type(exc).__name__}: {exc}"
    try:
        res.answer_relevancy = await answer_relevancy(
            report, scenario.log_chunk, ask=ask, embed=embed
        )
    except Exception as exc:  # noqa: BLE001
        res.error = (res.error or "") + f" relevancy: {type(exc).__name__}: {exc}"
    return res


def _mean(vals: list[float | None]) -> float | None:
    nums = [v for v in vals if v is not None]
    return round(sum(nums) / len(nums), 4) if nums else None


def _render_report(results: list[RagasResult], ablation: str) -> str:
    faith = _mean([r.faithfulness for r in results])
    rel = _mean([r.answer_relevancy for r in results])
    ctx = _mean([r.context_precision for r in results])
    lines = ["# RAG triad (RAGAS-style) evaluation — E4.1\n"]
    lines.append(f"Pipeline variant: **{ablation}** · scenarios: **{len(results)}**\n")
    lines.append("Reference-free metrics (re-implemented locally):\n")
    lines.append(f"- Mean **faithfulness**: {faith if faith is not None else '—'} "
                 "(claims grounded in retrieved context)")
    lines.append(f"- Mean **answer relevancy**: {rel if rel is not None else '—'} "
                 "(report-question vs log-chunk cosine)")
    lines.append(f"- Mean **context precision**: {ctx if ctx is not None else '—'} "
                 "(rank-aware AP of retrieved vs cited)\n")
    lines.append("| id | faithfulness | answer relevancy | context precision | retrieved/used | error |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        f = "—" if r.faithfulness is None else f"{r.faithfulness} ({r.faithful_supported}/{r.faithful_total})"
        rel_s = "—" if r.answer_relevancy is None else str(r.answer_relevancy)
        ctx_s = "—" if r.context_precision is None else str(r.context_precision)
        lines.append(
            f"| {r.id} | {f} | {rel_s} | {ctx_s} | {r.n_retrieved}/{r.n_used} | {r.error or ''} |"
        )
    lines.append("")
    lines.append("## Notes\n")
    lines.append("- Faithfulness / context precision are N/A (—) for no-retrieval "
                 "variants (no_rag, cot_only): there is no retrieved context to "
                 "ground against.")
    lines.append("- Context precision uses the reasoning agent's `used_incident_ids` "
                 "as the relevance proxy and computes rank-aware average precision.")
    return "\n".join(lines) + "\n"


async def amain(args: argparse.Namespace) -> int:
    if args.ablation in DETERMINISTIC_ABLATIONS:
        print(f"--ablation {args.ablation} produces no LLM report/reasoning; "
              "RAGAS does not apply.", file=sys.stderr)
        return 2

    scenarios = load_scenarios(args.dataset)
    if args.limit > 0:
        scenarios = scenarios[: args.limit]
    progress = args.progress_json
    n = len(scenarios)
    print(f"RAGAS eval: {n} scenarios, ablation={args.ablation}", file=sys.stderr)
    emit_progress(progress, event="run_start", kind="ragas", total=n, ablation=args.ablation)

    ask = make_ask()
    embed = _make_embed()

    results: list[RagasResult] = []
    for i, sc in enumerate(scenarios, 1):
        print(f"  [{i}/{n}] {sc.id}", file=sys.stderr, flush=True)
        emit_progress(progress, event="scenario_start", i=i, n=n, id=sc.id)
        # Retry the scenario on transient Gemini errors (503/429/timeout) so a
        # demand spike doesn't poison the metrics, mirroring evaluate.py.
        r = await run_with_retry(
            partial(score_scenario, sc, args.ablation, ask=ask, embed=embed),
            error_of=lambda res: res.error,
            label=sc.id,
            retries=args.retries,
            base_delay=args.retry_delay,
        )
        results.append(r)
        emit_progress(
            progress, event="scenario_done", i=i, n=n, id=sc.id,
            faithfulness=r.faithfulness, answer_relevancy=r.answer_relevancy,
            context_precision=r.context_precision, error=r.error,
        )

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    md_path = write_report(
        EXPERIMENTS_DIR,
        f"ragas-{args.ablation}-{timestamp}.md",
        _render_report(results, args.ablation),
    )
    emit_progress(
        progress,
        event="run_done",
        summary={
            "faithfulness": _mean([r.faithfulness for r in results]),
            "answer_relevancy": _mean([r.answer_relevancy for r in results]),
            "context_precision": _mean([r.context_precision for r in results]),
        },
        md_path=str(md_path),
    )
    if not progress:
        print(json.dumps([asdict(r) for r in results], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=0, help="First N scenarios (0=all).")
    parser.add_argument("--ablation", choices=ABLATIONS, default="none")
    parser.add_argument("--progress-json", action="store_true")
    parser.add_argument(
        "--retries", type=int, default=3,
        help="Retry a scenario up to N times on transient Gemini errors.",
    )
    parser.add_argument(
        "--retry-delay", type=float, default=5.0,
        help="Base backoff seconds for --retries (doubles each attempt).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
