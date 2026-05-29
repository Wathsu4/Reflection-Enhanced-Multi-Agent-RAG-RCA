"""Pairwise LLM-judge with position-bias mitigation (E4.2).

Compares two pipeline variants head-to-head on each scenario using their
*already-produced* final reports (read from the Day-2 result JSON files --
no pipeline re-run). For each scenario we ask Gemini which report is
better, **3 times in A/B order and 3 times in B/A order**, with an
explicit "ignore position and length" instruction (OWL / Zheng et al.
bias-mitigation template). Verdicts are normalised back to the real
variants and aggregated by 6-vote majority.

Balanced permutation (equal A/B and B/A samples) is the key mitigation
for the position bias documented in Zheng et al. 2024; we also report how
often swapping the order flipped the verdict (a direct bias diagnostic).

The judge is reference-based: it sees the curated ground-truth root cause.

Writes a markdown report to `eval/experiments/pairwise-{a}-vs-{b}-{ts}.md`.

Usage:
    uv run python scripts/evaluate_pairwise.py                       # none vs cot_only
    uv run python scripts/evaluate_pairwise.py --variant-a none --variant-b reflection_off
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.ablations import ABLATIONS  # noqa: E402
from rca_system.settings import settings  # noqa: E402

import os  # noqa: E402

if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
if not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = settings.google_genai_use_vertexai

from scripts.evaluate import (  # noqa: E402
    _emit_progress,
    _is_transient_error,
    load_scenarios,
)

EVAL_DIR = PROJECT_ROOT / "eval"
EXPERIMENTS_DIR = EVAL_DIR / "experiments"
DEFAULT_DATASET = EVAL_DIR / "incidents.jsonl"

AskFn = Callable[[str, float], Awaitable[str]]


# -------------------- result-file discovery --------------------


def _result_glob(variant: str) -> str:
    """Where a variant's pipeline result JSONs live (none -> eval/, else
    eval/experiments/)."""
    if variant == "none":
        return str(EVAL_DIR / "results-*.json")
    return str(EXPERIMENTS_DIR / f"results-{variant}-*.json")


def load_variant_reports(variant: str) -> dict[str, str]:
    """Return {scenario_id: final_markdown} from the newest result JSON for
    `variant`. Empty dict if none found."""
    matches = sorted(glob.glob(_result_glob(variant)), key=os.path.getmtime, reverse=True)
    if not matches:
        return {}
    data = json.loads(Path(matches[0]).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for r in data.get("results", []):
        md = r.get("final_markdown") or ""
        if r.get("id") and md.strip():
            out[str(r["id"])] = md
    return out


# -------------------- judge --------------------


def _judge_prompt(chunk: str, ground_truth: str, first: str, second: str) -> str:
    return (
        "You are a strict, impartial reviewer comparing TWO root-cause-analysis "
        "reports written for the SAME incident.\n\n"
        "Decide which report is better: more correct vs the ground truth, more "
        "specific, and more actionable.\n"
        "IMPORTANT: ignore the order the reports are presented in, and ignore "
        "their length. Judge only quality.\n"
        "Answer with EXACTLY one token: A, B, or tie.\n\n"
        f"INCIDENT LOG:\n{chunk}\n\n"
        f"GROUND-TRUTH ROOT CAUSE:\n{ground_truth}\n\n"
        f"REPORT A:\n{first}\n\n"
        f"REPORT B:\n{second}\n"
    )


def normalize_verdict(token: str, swapped: bool) -> str:
    """Map a raw 'A'/'B'/'tie' token to the real variant.

    Returns 'a' (variant_a wins), 'b' (variant_b wins), or 'tie'. When the
    presentation order was swapped (variant_b shown as "A"), invert A/B.
    """
    t = (token or "").strip().lower()
    first = t[:1]
    if first == "a":
        side = "a"
    elif first == "b":
        side = "b"
    else:
        return "tie"
    if swapped:
        side = "b" if side == "a" else "a"
    return side


def aggregate_votes(votes: list[str]) -> str:
    """Majority of 'a'/'b'/'tie'. Ties between a and b -> 'tie'."""
    a = votes.count("a")
    b = votes.count("b")
    if a > b:
        return "a"
    if b > a:
        return "b"
    return "tie"


@dataclass
class PairResult:
    id: str
    winner: str = "tie"  # 'a' / 'b' / 'tie'
    votes: list[str] = field(default_factory=list)
    order_consistent: bool = True  # did A/B-order and B/A-order agree?
    error: str | None = None


async def judge_scenario(
    scenario_id: str,
    chunk: str,
    ground_truth: str,
    report_a: str,
    report_b: str,
    *,
    ask: AskFn,
    n_each: int = 3,
    temperature: float = 0.7,
) -> PairResult:
    """Run the balanced-permutation judge for one scenario."""
    res = PairResult(id=scenario_id)
    ab_votes: list[str] = []
    ba_votes: list[str] = []
    try:
        for _ in range(n_each):
            raw = await ask(_judge_prompt(chunk, ground_truth, report_a, report_b), temperature)
            ab_votes.append(normalize_verdict(raw, swapped=False))
        for _ in range(n_each):
            raw = await ask(_judge_prompt(chunk, ground_truth, report_b, report_a), temperature)
            ba_votes.append(normalize_verdict(raw, swapped=True))
    except Exception as exc:  # noqa: BLE001
        res.error = f"{type(exc).__name__}: {exc}"
        return res
    res.votes = ab_votes + ba_votes
    res.winner = aggregate_votes(res.votes)
    res.order_consistent = aggregate_votes(ab_votes) == aggregate_votes(ba_votes)
    return res


def _make_ask() -> AskFn:
    from google import genai
    from google.genai import types as gt

    client = genai.Client(api_key=settings.google_api_key)

    async def ask(prompt: str, temperature: float) -> str:
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=gt.GenerateContentConfig(temperature=temperature),
        )
        return resp.text or ""

    return ask


# -------------------- report --------------------


def _render_report(
    results: list[PairResult], variant_a: str, variant_b: str
) -> str:
    a_wins = sum(1 for r in results if r.winner == "a" and not r.error)
    b_wins = sum(1 for r in results if r.winner == "b" and not r.error)
    ties = sum(1 for r in results if r.winner == "tie" and not r.error)
    scored = a_wins + b_wins + ties
    errs = sum(1 for r in results if r.error)
    inconsistent = sum(1 for r in results if not r.order_consistent and not r.error)

    def pct(x: int) -> str:
        return f"{(x / scored * 100):.0f}%" if scored else "—"

    lines = ["# Pairwise LLM-judge (bias-mitigated) — E4.2\n"]
    lines.append(f"**A = `{variant_a}`** vs **B = `{variant_b}`** · "
                 f"{scored} scenarios scored ({errs} errored)\n")
    lines.append("6 votes/scenario (3 A/B + 3 B/A), explicit "
                 "ignore-position-and-length instruction, reference-based.\n")
    lines.append(f"- **A ({variant_a}) wins:** {a_wins} ({pct(a_wins)})")
    lines.append(f"- **B ({variant_b}) wins:** {b_wins} ({pct(b_wins)})")
    lines.append(f"- **Ties:** {ties} ({pct(ties)})")
    lines.append(f"- **Order-inconsistent** (A/B vs B/A majority disagreed): "
                 f"{inconsistent}/{scored} — lower is less position bias\n")
    lines.append("| id | winner | votes (a/b/tie) | order-consistent | error |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        a = r.votes.count("a")
        b = r.votes.count("b")
        t = r.votes.count("tie")
        win = {"a": variant_a, "b": variant_b, "tie": "tie"}[r.winner]
        lines.append(
            f"| {r.id} | {win if not r.error else '—'} | {a}/{b}/{t} | "
            f"{'yes' if r.order_consistent else 'NO'} | {r.error or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


async def amain(args: argparse.Namespace) -> int:
    va, vb = args.variant_a, args.variant_b
    if va == vb:
        print("variant-a and variant-b must differ", file=sys.stderr)
        return 2

    reports_a = load_variant_reports(va)
    reports_b = load_variant_reports(vb)
    if not reports_a:
        print(f"no result file for variant {va!r}; run it first "
              f"(scripts/evaluate.py --ablation {va}).", file=sys.stderr)
        return 2
    if not reports_b:
        print(f"no result file for variant {vb!r}; run it first.", file=sys.stderr)
        return 2

    scenarios = load_scenarios(args.dataset)
    gt = {s.id: s for s in scenarios}
    matched = [s for s in scenarios if s.id in reports_a and s.id in reports_b]
    if args.limit > 0:
        matched = matched[: args.limit]
    progress = args.progress_json
    n = len(matched)
    print(f"Pairwise: {va} vs {vb}, {n} matched scenarios", file=sys.stderr)
    _emit_progress(progress, event="run_start", kind="pairwise", total=n,
                   variant_a=va, variant_b=vb)

    ask = _make_ask()
    results: list[PairResult] = []
    for i, s in enumerate(matched, 1):
        print(f"  [{i}/{n}] {s.id}", file=sys.stderr, flush=True)
        _emit_progress(progress, event="scenario_start", i=i, n=n, id=s.id)
        r = await judge_scenario(
            s.id, s.log_chunk, gt[s.id].ground_truth_root_cause,
            reports_a[s.id], reports_b[s.id], ask=ask,
        )
        attempt = 0
        while _is_transient_error(r.error) and attempt < args.retries:
            delay = args.retry_delay * (2**attempt)
            print(f"      transient error on {s.id}; retry {attempt + 1}/{args.retries} "
                  f"in {delay:.0f}s", file=sys.stderr, flush=True)
            await asyncio.sleep(delay)
            attempt += 1
            r = await judge_scenario(
                s.id, s.log_chunk, gt[s.id].ground_truth_root_cause,
                reports_a[s.id], reports_b[s.id], ask=ask,
            )
        results.append(r)
        _emit_progress(progress, event="scenario_done", i=i, n=n, id=s.id,
                       winner=r.winner, error=r.error)

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    md_path = EXPERIMENTS_DIR / f"pairwise-{va}-vs-{vb}-{timestamp}.md"
    md_path.write_text(_render_report(results, va, vb), encoding="utf-8")
    print(f"Wrote {md_path}", file=sys.stderr)
    a_wins = sum(1 for r in results if r.winner == "a" and not r.error)
    b_wins = sum(1 for r in results if r.winner == "b" and not r.error)
    _emit_progress(progress, event="run_done",
                   summary={"a_wins": a_wins, "b_wins": b_wins,
                            "variant_a": va, "variant_b": vb},
                   md_path=str(md_path))
    if not progress:
        print(json.dumps([asdict(r) for r in results], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--variant-a", choices=ABLATIONS, default="none")
    parser.add_argument("--variant-b", choices=ABLATIONS, default="cot_only")
    parser.add_argument("--limit", type=int, default=0, help="First N matched scenarios (0=all).")
    parser.add_argument("--progress-json", action="store_true")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    args = parser.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
