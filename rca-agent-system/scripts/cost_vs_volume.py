"""Cost-vs-volume simulation for the classifier gate (RQ4 / E6.3).

The headline efficiency claim: a cheap classifier gating an expensive
multi-agent pipeline makes compute scale with the *incident rate*, not the
total log volume. This is a deterministic simulation -- **no Gemini calls**
-- so it runs instantly and reproducibly.

Model: a stream of `total_chunks` log chunks at `incident_pct`% incident
rate. The classifier runs on every chunk (cheap, ~tens of ms) but only
incident chunks trigger the RCA pipeline (expensive, several Gemini calls).
We compare the gated policy (our system) against an ungated baseline that
runs RCA on every chunk.

Writes a markdown report to `eval/experiments/cost-vs-volume-{ts}.md`.

Usage:
    uv run python scripts/cost_vs_volume.py
    uv run python scripts/cost_vs_volume.py --total-chunks 5000 --incident-pct 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / "eval"
EXPERIMENTS_DIR = EVAL_DIR / "experiments"


def _emit_progress(enabled: bool, **fields: Any) -> None:
    if not enabled:
        return
    print(json.dumps(fields, default=str), flush=True)


def simulate(
    total_chunks: int,
    incident_pct: float,
    calls_per_rca: int,
    classifier_ms: float = 50.0,
    rca_seconds: float = 28.0,
) -> dict[str, Any]:
    """Compute gated vs ungated Gemini-call counts and wall-time for a stream.

    Returns a dict of the headline figures. Purely arithmetic.
    """
    incidents = round(total_chunks * incident_pct / 100.0)

    gated_gemini = incidents * calls_per_rca
    ungated_gemini = total_chunks * calls_per_rca
    saved_gemini = ungated_gemini - gated_gemini
    reduction_factor = (ungated_gemini / gated_gemini) if gated_gemini else float("inf")

    # Wall-time: gated pays cheap classifier on every chunk + RCA on
    # incidents; ungated pays RCA on every chunk (no gate).
    gated_wall_s = total_chunks * (classifier_ms / 1000.0) + incidents * rca_seconds
    ungated_wall_s = total_chunks * rca_seconds
    speedup = (ungated_wall_s / gated_wall_s) if gated_wall_s else float("inf")

    return {
        "total_chunks": total_chunks,
        "incident_pct": incident_pct,
        "incidents": incidents,
        "calls_per_rca": calls_per_rca,
        "classifier_ms": classifier_ms,
        "rca_seconds": rca_seconds,
        "gated_gemini_calls": gated_gemini,
        "ungated_gemini_calls": ungated_gemini,
        "saved_gemini_calls": saved_gemini,
        "reduction_factor": round(reduction_factor, 2),
        "classifier_inferences": total_chunks,
        "gated_wall_s": round(gated_wall_s, 1),
        "ungated_wall_s": round(ungated_wall_s, 1),
        "wall_speedup": round(speedup, 2),
    }


def _render_report(s: dict[str, Any]) -> str:
    lines = ["# Cost-vs-volume simulation (gate) — RQ4 / E6.3\n"]
    lines.append(
        f"Stream of **{s['total_chunks']}** chunks at **{s['incident_pct']}%** "
        f"incident rate (**{s['incidents']}** incidents), "
        f"**{s['calls_per_rca']}** Gemini calls per RCA. No Gemini calls were "
        "made -- this is a deterministic simulation.\n"
    )
    lines.append("## Headline\n")
    lines.append(
        f"- Gemini calls **gated** (our system): **{s['gated_gemini_calls']}**")
    lines.append(
        f"- Gemini calls **ungated** (RCA on every chunk): "
        f"**{s['ungated_gemini_calls']}**")
    lines.append(
        f"- **Reduction: {s['reduction_factor']}x fewer Gemini calls** "
        f"({s['saved_gemini_calls']} calls saved)")
    lines.append(
        f"- Classifier inferences (cheap, ~{s['classifier_ms']:.0f} ms each): "
        f"{s['classifier_inferences']}\n")
    lines.append("## Wall-time model\n")
    lines.append("| Policy | classifier | RCA runs | est. wall time |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Gated (ours) | {s['total_chunks']} chunks | {s['incidents']} | "
        f"{s['gated_wall_s']} s |")
    lines.append(
        f"| Ungated | — | {s['total_chunks']} | {s['ungated_wall_s']} s |")
    lines.append(f"\nEstimated **{s['wall_speedup']}x** wall-time speedup at "
                 f"~{s['rca_seconds']:.0f}s per RCA.\n")
    lines.append("## Why this defends RQ4\n")
    lines.append(
        "Gated compute scales with the incident count, not the log volume: "
        f"the {s['reduction_factor']}x Gemini-call reduction equals the "
        "volume-to-incident ratio (100 / incident_pct). The classifier gate "
        "is itself cheap and accurate (see the classifier-metrics card: macro "
        "F1 ~0.95 on the held-out test split), so it rarely wastes an RCA on a "
        "non-incident or misses a real one.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total-chunks", type=int, default=1000)
    parser.add_argument("--incident-pct", type=float, default=5.0)
    parser.add_argument("--calls-per-rca", type=int, default=4)
    parser.add_argument("--classifier-ms", type=float, default=50.0)
    parser.add_argument("--rca-seconds", type=float, default=28.0)
    parser.add_argument("--progress-json", action="store_true")
    args = parser.parse_args(argv)
    progress = args.progress_json

    _emit_progress(progress, event="run_start", kind="cost_vs_volume", total=1)
    _emit_progress(progress, event="scenario_start", i=1, n=1, id="simulation")
    s = simulate(
        args.total_chunks, args.incident_pct, args.calls_per_rca,
        args.classifier_ms, args.rca_seconds,
    )
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    md_path = EXPERIMENTS_DIR / f"cost-vs-volume-{timestamp}.md"
    md_path.write_text(_render_report(s), encoding="utf-8")
    print(f"Wrote {md_path}", file=sys.stderr)
    _emit_progress(progress, event="scenario_done", i=1, n=1, id="simulation", error=None)
    _emit_progress(progress, event="run_done", summary=s, md_path=str(md_path))
    if not progress:
        print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
