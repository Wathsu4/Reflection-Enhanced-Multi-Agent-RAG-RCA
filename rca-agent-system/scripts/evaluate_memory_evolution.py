"""Show that the memory's `success_score` evolves correctly over time.

This is the headline experiment for the thesis novelty claim: that the
reflection agent's adjustments accumulate into a useful re-ranking
signal. Without this, our re-ranking step is a no-op.

Procedure:
  1. Reset the knowledge base to the seed state (all scores = 1.0).
  2. Snapshot every incident's score.
  3. Run the in-domain subset of the eval dataset twice, end-to-end,
     through the four-agent pipeline. Each run mutates scores via the
     reflection -> memory_update agents.
  4. Snapshot scores again.
  5. Emit a table showing per-incident: baseline -> after-run-1 ->
     after-run-2, plus an aggregate "drift sign" check:
       - in-domain (helpful) incidents should trend > 1.0,
       - others should stay <= 1.0.

Side note: this script intentionally runs the *same* incidents twice
to demonstrate the *trend*. A single run is necessarily noisy (one
Gemini sample); two runs over the same set lets us see whether the
score signal is reproducible in direction.

Outputs:
  * `eval/memory-evolution-{timestamp}.md` -- thesis-ready table

Usage:
    uv run python scripts/evaluate_memory_evolution.py
    uv run python scripts/evaluate_memory_evolution.py --runs 1
    uv run python scripts/evaluate_memory_evolution.py --skip-reset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.ablations import ABLATIONS, DETERMINISTIC_ABLATIONS, build_root_agent  # noqa: E402
from rca_system.memory.chroma_store import IncidentMemory  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "eval"
# Non-default ablation runs are experiments; keep them out of the
# demo-ready eval/memory-evolution-*.md reports.
EXPERIMENTS_DIR = EVAL_DIR / "experiments"
DEFAULT_DATASET = EVAL_DIR / "incidents.jsonl"


def _emit_progress(enabled: bool, **fields: Any) -> None:
    """Emit one compact JSON lifecycle line to stdout when `--progress-json`
    is set, for the eval-console JobManager. Human logging stays on stderr."""
    if not enabled:
        return
    print(json.dumps(fields, default=str), flush=True)


def _load_in_domain(path: Path) -> list[dict[str, Any]]:
    """Filter the eval dataset to scenarios with a known expected
    incident id (i.e. excludes OOD cases). Memory-evolution doesn't
    have a clean expectation for OOD inputs."""
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("expected_incident_id"):
            out.append(d)
    return out


def _snapshot_scores() -> dict[str, float]:
    """Pull the current `success_score` for every record. Uses a
    direct Chroma `get` since `IncidentMemory.query` ranks by
    similarity which would only return top-k."""
    mem = IncidentMemory()
    raw = mem._collection.get(include=["metadatas"])  # noqa: SLF001
    ids = raw.get("ids") or []
    metas = raw.get("metadatas") or []
    out: dict[str, float] = {}
    for incident_id, meta in zip(ids, metas):
        m = meta or {}
        out[str(incident_id)] = round(float(m.get("success_score", 1.0)), 3)
    return out


async def _run_pipeline(scenario: dict[str, Any], ablation: str = "none") -> bool:
    """Execute the pipeline variant for one scenario. Returns True on success."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    agent = build_root_agent(ablation)

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="rca_system", user_id="memory-eval"
    )
    runner = Runner(
        agent=agent,
        app_name="rca_system",
        session_service=session_service,
    )
    msg = Content(role="user", parts=[Part(text=scenario["log_chunk"])])
    try:
        async for _ in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=msg,
        ):
            pass
    except Exception as exc:
        print(
            f"      ! pipeline error on {scenario['id']}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def _render_report(
    snapshots: list[dict[str, float]],
    scenario_ids: list[str],
    ablation: str = "none",
) -> str:
    headers = ["incident_id"] + [f"after run {i}" for i in range(len(snapshots))]
    headers[0] = "incident_id"
    headers[1] = "baseline"
    rows: list[str] = []
    incident_ids = sorted(snapshots[0].keys())
    for iid in incident_ids:
        cells = [f"`{iid}`"]
        for snap in snapshots:
            cells.append(f"{snap.get(iid, 1.0):.3f}")
        rows.append("| " + " | ".join(cells) + " |")

    lines: list[str] = []
    lines.append("# Memory-evolution evaluation\n")
    lines.append(f"Pipeline variant (ablation): **{ablation}**\n")
    lines.append(
        f"Ran the in-domain subset ({len(scenario_ids)} scenarios) "
        f"through the pipeline {len(snapshots) - 1} time(s). Scores below "
        "are the dynamic `success_score` field maintained by the "
        "reflection + memory_update agents."
    )
    lines.append(
        "\nExpected pattern: incidents that the reasoning agent "
        "*correctly* leans on get boosted (>1.0); incidents retrieved "
        "but judged irrelevant get demoted (<1.0). All starting from "
        "the seed value of 1.0.\n"
    )
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    lines.extend(rows)

    # Aggregate drift summary -- final snapshot vs baseline.
    if len(snapshots) >= 2:
        baseline, final = snapshots[0], snapshots[-1]
        ups = sum(1 for k, v in final.items() if v > baseline.get(k, 1.0))
        downs = sum(1 for k, v in final.items() if v < baseline.get(k, 1.0))
        flat = sum(1 for k, v in final.items() if v == baseline.get(k, 1.0))
        lines.append(
            f"\n**Drift summary (final vs baseline):** "
            f"{ups} incident(s) boosted, {downs} demoted, {flat} unchanged."
        )

    lines.append("\n## Scenarios used\n")
    for sid in scenario_ids:
        lines.append(f"- `{sid}`")
    lines.append("")
    return "\n".join(lines)


async def amain(args: argparse.Namespace) -> int:
    if not args.skip_reset:
        # Delegate to the production reset script -- it handles the
        # chromadb cache + Windows mmap-handle release correctly.
        from scripts.reset_memory import reset_memory

        rc = reset_memory()
        if rc != 0:
            print("seeder failed; aborting", file=sys.stderr)
            return 1

    scenarios = _load_in_domain(args.dataset)
    if args.limit > 0:
        scenarios = scenarios[: args.limit]
    progress = args.progress_json
    n = len(scenarios)
    total_steps = n * args.runs
    print(
        f"Memory-evolution eval: {n} scenarios, {args.runs} run(s)",
        file=sys.stderr,
    )
    _emit_progress(
        progress,
        event="run_start",
        kind="memory_evolution",
        total=total_steps,
        scenarios=n,
        runs=args.runs,
        ablation=args.ablation,
    )

    step = 0
    snapshots: list[dict[str, float]] = [_snapshot_scores()]
    for run_idx in range(1, args.runs + 1):
        print(f"\n=== run {run_idx}/{args.runs} ===", file=sys.stderr)
        for i, sc in enumerate(scenarios, 1):
            step += 1
            print(f"  [{i}/{n}] {sc['id']}", file=sys.stderr, flush=True)
            _emit_progress(
                progress,
                event="scenario_start",
                i=step,
                n=total_steps,
                id=sc["id"],
                run=run_idx,
            )
            ok = await _run_pipeline(sc, ablation=args.ablation)
            _emit_progress(
                progress,
                event="scenario_done",
                i=step,
                n=total_steps,
                id=sc["id"],
                run=run_idx,
                error=None if ok else "pipeline_error",
            )
        snapshots.append(_snapshot_scores())

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    md = _render_report(snapshots, [sc["id"] for sc in scenarios], args.ablation)
    if args.ablation == "none":
        out_dir = EVAL_DIR
        stem = f"memory-evolution-{timestamp}"
    else:
        out_dir = EXPERIMENTS_DIR
        stem = f"memory-evolution-{args.ablation}-{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{stem}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"\nWrote {md_path}", file=sys.stderr)
    # Drift summary for the run_done event.
    baseline, final = snapshots[0], snapshots[-1]
    drift = {
        "boosted": sum(1 for k, v in final.items() if v > baseline.get(k, 1.0)),
        "demoted": sum(1 for k, v in final.items() if v < baseline.get(k, 1.0)),
        "unchanged": sum(1 for k, v in final.items() if v == baseline.get(k, 1.0)),
    }
    _emit_progress(
        progress,
        event="run_done",
        summary={"drift": drift, "snapshots": snapshots},
        md_path=str(md_path),
    )
    if not progress:
        print(md)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="JSONL of scenarios (default: eval/incidents.jsonl).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="How many times to iterate over the scenario set. "
             "Two runs is enough to show repeatable drift direction.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit to first N in-domain scenarios (0 = all).",
    )
    parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="Don't wipe + reseed before measuring (use this if you "
             "want to observe drift on top of an existing state).",
    )
    parser.add_argument(
        "--ablation",
        choices=ABLATIONS,
        default="none",
        help=(
            "Pipeline variant (default: none = full system). Useful "
            "contrasts here are reflection_off and memory_frozen, which "
            "should show flat score drift vs the full pipeline. Non-default "
            "variants write to eval/experiments/."
        ),
    )
    parser.add_argument(
        "--progress-json",
        action="store_true",
        help=(
            "Emit machine-readable JSONL lifecycle events to stdout for the "
            "evaluation console to render live progress."
        ),
    )
    args = parser.parse_args(argv)
    if args.ablation in DETERMINISTIC_ABLATIONS:
        parser.error(
            f"--ablation {args.ablation} performs no LLM call and never "
            "mutates memory, so it has no meaningful score drift to measure."
        )
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
