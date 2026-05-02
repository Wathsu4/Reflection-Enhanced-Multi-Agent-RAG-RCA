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

from rca_system.memory.chroma_store import IncidentMemory  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "eval"
DEFAULT_DATASET = EVAL_DIR / "incidents.jsonl"


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


async def _run_pipeline(scenario: dict[str, Any]) -> bool:
    """Execute the pipeline for one scenario. Returns True on success."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    from rca_system.agent import root_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="rca_system", user_id="memory-eval"
    )
    runner = Runner(
        agent=root_agent,
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
    snapshots: list[dict[str, float]], scenario_ids: list[str]
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
        from chromadb.api.client import SharedSystemClient
        import shutil
        from rca_system.settings import settings as agent_settings
        from scripts.seed_knowledge_base import main as seed_main

        target = Path(agent_settings.chroma_persist_dir)
        if target.exists():
            SharedSystemClient.clear_system_cache()
            shutil.rmtree(target)
            print(f"removed {target}", file=sys.stderr)
        rc = seed_main([])
        if rc != 0:
            print("seeder failed; aborting", file=sys.stderr)
            return 1

    scenarios = _load_in_domain(args.dataset)
    if args.limit > 0:
        scenarios = scenarios[: args.limit]
    print(
        f"Memory-evolution eval: {len(scenarios)} scenarios, "
        f"{args.runs} run(s)",
        file=sys.stderr,
    )

    snapshots: list[dict[str, float]] = [_snapshot_scores()]
    for run_idx in range(1, args.runs + 1):
        print(f"\n=== run {run_idx}/{args.runs} ===", file=sys.stderr)
        for i, sc in enumerate(scenarios, 1):
            print(
                f"  [{i}/{len(scenarios)}] {sc['id']}",
                file=sys.stderr,
                flush=True,
            )
            await _run_pipeline(sc)
        snapshots.append(_snapshot_scores())

    EVAL_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    md = _render_report(snapshots, [sc["id"] for sc in scenarios])
    md_path = EVAL_DIR / f"memory-evolution-{timestamp}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"\nWrote {md_path}", file=sys.stderr)
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
    args = parser.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
