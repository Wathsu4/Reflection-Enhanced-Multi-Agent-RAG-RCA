"""Surface the ModernBERT classifier's test-split metrics (RQ4 / E7.1).

The classifier is fine-tuned offline (see the training notebook) and its
held-out test results are persisted to `training_metadata.json` alongside
the model. This script lifts those numbers into the evaluation console as
a markdown report, so the gating claim (RQ4) appears next to the agent
metrics instead of living only in the notebook.

It makes **no Gemini calls** and runs in milliseconds. Like the other eval
scripts it accepts `--progress-json` so the eval-console JobManager can
track it; it writes its report under `eval/experiments/`.

Usage:
    uv run python scripts/classifier_metrics.py
    uv run python scripts/classifier_metrics.py --metadata-path /path/to/training_metadata.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._eval_common import EXPERIMENTS_DIR, emit_progress, write_report  # noqa: E402

REPO_ROOT = PROJECT_ROOT.parent

# Default location of the fine-tuned model's training metadata.
DEFAULT_METADATA_PATH = (
    REPO_ROOT
    / "classifier-service"
    / "models"
    / "modernbert-log-severity-v1"
    / "training_metadata.json"
)

# Class order for the per-class table (matches the training label map).
_CLASS_ORDER = ["fatal_or_critical", "error", "warning", "normal"]
_CLASS_LABEL = {
    "fatal_or_critical": "FATAL_OR_CRITICAL",
    "error": "ERROR",
    "warning": "WARNING",
    "normal": "NORMAL",
}


def _fmt(v: Any, digits: int = 4) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _render_report(meta: dict[str, Any]) -> str:
    tr = meta.get("test_results", {}) or {}
    lines: list[str] = []
    lines.append("# Classifier metrics (gate) — RQ4 / E7.1\n")
    lines.append(
        f"Fine-tuned model: `{meta.get('model_id', 'unknown')}` · "
        f"data sources: {', '.join(meta.get('data_sources', []) or ['?'])} · "
        f"epochs run: {meta.get('epochs_run', '?')}\n"
    )
    lines.append("## Headline (held-out test split)\n")
    lines.append(f"- Accuracy: **{_fmt(tr.get('eval_accuracy'))}**")
    lines.append(f"- Macro F1: **{_fmt(tr.get('eval_f1_macro'))}**")
    lines.append(f"- Macro precision: **{_fmt(tr.get('eval_precision_macro'))}**")
    lines.append(f"- Macro recall: **{_fmt(tr.get('eval_recall_macro'))}**")
    lines.append("")
    lines.append("## Per-class\n")
    lines.append("| class | precision | recall | F1 | support |")
    lines.append("|---|---|---|---|---|")
    for c in _CLASS_ORDER:
        p = tr.get(f"eval_precision_{c}")
        r = tr.get(f"eval_recall_{c}")
        f1 = tr.get(f"eval_f1_{c}")
        sup = tr.get(f"eval_support_{c}")
        sup_str = str(int(sup)) if isinstance(sup, (int, float)) else "—"
        lines.append(
            f"| {_CLASS_LABEL[c]} | {_fmt(p)} | {_fmt(r)} | {_fmt(f1)} | {sup_str} |"
        )
    lines.append("")
    lines.append("## How this backs the gating claim (RQ4)\n")
    lines.append(
        "The classifier is the cheap first stage: it decides per chunk whether "
        "to invoke the expensive multi-agent RCA pipeline. High recall on "
        "FATAL/ERROR means few real incidents are missed; high precision means "
        "few wasted Gemini invocations. Per-chunk inference is sub-50 ms, so "
        "compute scales with the incident rate, not total log volume.\n"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--progress-json", action="store_true")
    args = parser.parse_args(argv)
    progress = args.progress_json

    emit_progress(progress, event="run_start", kind="classifier_metrics", total=1)
    emit_progress(progress, event="scenario_start", i=1, n=1, id="classifier-test-split")

    if not args.metadata_path.is_file():
        msg = (
            f"classifier metadata not found at {args.metadata_path}. The "
            "fine-tuned model is not in git; train it or point --metadata-path "
            "at an existing training_metadata.json."
        )
        print(msg, file=sys.stderr)
        emit_progress(progress, event="scenario_done", i=1, n=1, id="classifier-test-split", error=msg)
        return 2

    meta = json.loads(args.metadata_path.read_text(encoding="utf-8"))
    md = _render_report(meta)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    md_path = write_report(EXPERIMENTS_DIR, f"classifier-metrics-{timestamp}.md", md)

    tr = meta.get("test_results", {}) or {}
    emit_progress(progress, event="scenario_done", i=1, n=1, id="classifier-test-split", error=None)
    emit_progress(
        progress,
        event="run_done",
        summary={
            "accuracy": tr.get("eval_accuracy"),
            "f1_macro": tr.get("eval_f1_macro"),
        },
        md_path=str(md_path),
    )
    if not progress:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
