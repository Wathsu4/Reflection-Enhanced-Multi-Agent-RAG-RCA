"""Visualize labelled samples per dataset used by the log severity classifier.

This is a *no-ML* script that just reads the same raw / processed files the
training notebook uses and prints / writes labelled samples per dataset.

It demonstrates two things visually:

1. **BGL (raw)** — how the rule from the notebook turns a raw log line
   into one of 4 severity classes, and how a chunk of 30 lines inherits
   the worst severity in the window.
2. **BGL / Synthetic (processed JSONL)** — what the final
   `{text, label}` records the model actually trains on look like, per class.

It uses only the Python standard library, so it can be run on any machine
that has Python 3.9+ without installing anything.

USAGE
-----

    python helpful_scripts/visualize_data_and_labels.py

By default it auto-discovers data in a handful of sensible locations
(local raw_data/, processed_data/, synthetic_data/, and the Colab Drive
mount path from the notebook).

You can also point it at specific paths:

    python helpful_scripts/visualize_data_and_labels.py \\
        --bgl-raw            /path/to/BGL.log \\
        --bgl-processed-dir  /path/to/processed_data \\
        --synthetic-dir      /path/to/synthetic_jsonl_files \\
        --samples-per-class  3 \\
        --out                helpful_scripts/samples

If no data is found, the script still runs and produces a small inline
demo sample so the supervisor can see *what* the labelled output looks
like (just with placeholder log lines).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Labelling rules — copied verbatim from the notebook so this script is the
# single source of truth for "how do labels come into existence?".
# ---------------------------------------------------------------------------

LABEL_MAP = {
    "FATAL_OR_CRITICAL": 0,
    "ERROR": 1,
    "WARNING": 2,
    "NORMAL": 3,
}
ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}

# Lower number = more severe. Used for chunk-level "worst-case" labelling.
SEVERITY_PRIORITY = {
    "FATAL_OR_CRITICAL": 0,
    "ERROR": 1,
    "WARNING": 2,
    "NORMAL": 3,
}

CHUNK_SIZE = 30
CHUNK_STRIDE = 15


def classify_bgl_line(line: str) -> tuple[str, str]:
    """Classify a single BGL log line into a severity class.

    BGL format:
        <Label> <Timestamp> <Date> <Node> <DateTime> <NodeRepeat> <Type> <Component> <Level> <Content...>

    Returns
    -------
    (severity_label, cleaned_text_without_alert_tag)
    """
    line = line.strip()
    if not line:
        return "NORMAL", ""

    parts = line.split(None, 9)
    if len(parts) < 9:
        return "NORMAL", line

    alert_tag = parts[0]                  # "-" or alert category (e.g. KERNDTLB)
    level = parts[8].upper() if len(parts) > 8 else ""

    # Drop the alert-tag column so the model can't trivially cheat by reading "-"
    cleaned = " ".join(parts[1:])

    if level in ("FATAL", "FAILURE", "SEVERE"):
        return "FATAL_OR_CRITICAL", cleaned
    if level == "ERROR":
        return "ERROR", cleaned
    if level in ("WARNING", "WARN"):
        return "WARNING", cleaned
    if alert_tag != "-":
        # Has an alert tag but level is INFO -> still an anomaly, treat as ERROR
        return "ERROR", cleaned
    return "NORMAL", cleaned


def chunk_label(severities: list[str]) -> str:
    """Return the worst (most severe) label in a window."""
    return min(severities, key=lambda s: SEVERITY_PRIORITY[s])


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

BGL_RAW_CANDIDATES = [
    REPO_ROOT / "raw_data" / "BGL.log",
    REPO_ROOT / "data" / "BGL.log",
    REPO_ROOT / "BGL.log",
    Path.home() / "Downloads" / "BGL.log",
    Path("/content/drive/MyDrive/log_severity_classifier/raw_data/BGL.log"),
]

BGL_PROCESSED_CANDIDATES = [
    REPO_ROOT / "processed_data",
    REPO_ROOT / "data" / "processed",
    Path("/content/drive/MyDrive/log_severity_classifier/processed_data"),
]

SYNTHETIC_CANDIDATES = [
    REPO_ROOT / "synthetic_data",
    REPO_ROOT / "data" / "synthetic",
    REPO_ROOT / "synthetic_raw",
    Path("/content/synthetic_raw"),
]


def first_existing(paths: Iterable[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

LINE = "-" * 78
HEAVY = "=" * 78


def banner(title: str) -> str:
    return f"\n{HEAVY}\n{title}\n{HEAVY}\n"


def repo_rel(p: Path) -> str:
    """Show `p` relative to the repo root if possible, else absolute."""
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def short(text: str, width: int = 200) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= width:
        return text
    return text[:width].rstrip() + " ..."


def fmt_distribution(counter: Counter) -> str:
    total = sum(counter.values()) or 1
    out = []
    for name in ("FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"):
        c = counter.get(name, 0)
        out.append(f"  {name:<20} {c:>10,}  ({100 * c / total:5.2f}%)")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 1. BGL raw view (line-level + chunk-level)
# ---------------------------------------------------------------------------

def visualize_bgl_raw(
    bgl_path: Path,
    max_lines: int,
    samples_per_class: int,
    out_dir: Path,
) -> str:
    """Read raw BGL.log, label every line, build chunks, show samples per class.

    Returns the markdown report (also written to disk).
    """
    print(banner(f"BGL — raw lines  ({bgl_path})"))

    parsed: list[tuple[str, str]] = []
    with bgl_path.open("r", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            sev, text = classify_bgl_line(line)
            if text:
                parsed.append((sev, text))

    line_counter = Counter(s for s, _ in parsed)
    print(f"Parsed {len(parsed):,} lines (capped at --max-raw-lines={max_lines:,})\n")
    print("Per-line label distribution:")
    print(fmt_distribution(line_counter))

    # ----- pick samples per class (line-level) -----
    line_samples_by_class: dict[str, list[str]] = defaultdict(list)
    for sev, text in parsed:
        if len(line_samples_by_class[sev]) < samples_per_class:
            line_samples_by_class[sev].append(text)
        if all(len(line_samples_by_class[c]) >= samples_per_class for c in LABEL_MAP):
            break

    # ----- build chunks (30 lines, stride 15) -----
    chunks = []
    for start in range(0, len(parsed) - CHUNK_SIZE + 1, CHUNK_STRIDE):
        window = parsed[start : start + CHUNK_SIZE]
        sevs = [s for s, _ in window]
        worst = chunk_label(sevs)
        chunks.append({
            "label_name": worst,
            "label": LABEL_MAP[worst],
            "text": "\n".join(t for _, t in window),
            "line_severities": sevs,
        })

    chunk_counter = Counter(c["label_name"] for c in chunks)
    print(f"\nBuilt {len(chunks):,} chunks "
          f"(size={CHUNK_SIZE} lines, stride={CHUNK_STRIDE})\n")
    print("Per-chunk label distribution:")
    print(fmt_distribution(chunk_counter))

    chunk_samples_by_class: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        if len(chunk_samples_by_class[c["label_name"]]) < samples_per_class:
            chunk_samples_by_class[c["label_name"]].append(c)

    # ----- assemble markdown report -----
    md: list[str] = []
    md.append("# BGL — raw view\n")
    md.append(f"Source file: `{bgl_path}`\n")
    md.append(f"Lines parsed: **{len(parsed):,}**  "
              f"(capped at `--max-raw-lines={max_lines:,}`)\n")
    md.append(f"Chunks built: **{len(chunks):,}**  "
              f"(chunk size = {CHUNK_SIZE} lines, stride = {CHUNK_STRIDE})\n")
    md.append("\n## Per-line label distribution\n```\n"
              + fmt_distribution(line_counter) + "\n```\n")
    md.append("## Per-chunk label distribution\n```\n"
              + fmt_distribution(chunk_counter) + "\n```\n")

    md.append("## Sample raw lines per class\n")
    md.append("These are individual log lines, after we strip the BGL "
              "`alert tag` column. The label on the right is what our "
              "rule extracted from the `Level` token in the raw line.\n")
    for sev in ("FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"):
        md.append(f"### Label = `{sev}`  (id={LABEL_MAP[sev]})\n")
        if not line_samples_by_class[sev]:
            md.append("_no examples in this slice of the data_\n")
            continue
        for t in line_samples_by_class[sev]:
            md.append(f"- `{short(t, 220)}`")
        md.append("")

    md.append("## Sample chunks per class\n")
    md.append(f"A chunk is **{CHUNK_SIZE} consecutive lines**. The chunk "
              "label is the **worst severity** seen anywhere in the window "
              "(if any line is `ERROR`, the chunk is `ERROR`, etc.).\n")
    for sev in ("FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"):
        md.append(f"### Chunk label = `{sev}`  (id={LABEL_MAP[sev]})\n")
        examples = chunk_samples_by_class[sev]
        if not examples:
            md.append("_no examples in this slice of the data_\n")
            continue
        for i, c in enumerate(examples, 1):
            md.append(f"**Example {i}** — line-level breakdown inside the chunk: "
                      f"`{dict(Counter(c['line_severities']))}`\n")
            md.append("```text")
            md.append(short(c["text"], 600))
            md.append("```\n")

    # ----- also print a short console preview -----
    print("\nSample chunks per class (first example only, truncated):")
    for sev in ("FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"):
        ex = chunk_samples_by_class[sev]
        if ex:
            print(f"\n  [{sev}]  -> id={LABEL_MAP[sev]}")
            print(textwrap.indent(short(ex[0]['text'], 240), "      "))
        else:
            print(f"\n  [{sev}]  -> id={LABEL_MAP[sev]}  (no examples in this slice)")

    report = "\n".join(md) + "\n"
    out_path = out_dir / "bgl_raw_sample.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote {repo_rel(out_path)}")
    return report


# ---------------------------------------------------------------------------
# 2. Pre-processed JSONL view (BGL or Synthetic)
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def visualize_jsonl_dataset(
    dataset_name: str,
    files: list[Path],
    samples_per_class: int,
    out_dir: Path,
    out_filename: str,
) -> str | None:
    """Generic JSONL viewer. Expects records with `text` and `label` keys."""
    if not files:
        return None

    print(banner(f"{dataset_name} — processed JSONL"))
    for fp in files:
        print(f"  source: {fp}")

    all_items: list[dict] = []
    for fp in files:
        items = load_jsonl(fp)
        # If the record doesn't have `label_name`, derive it from `label`.
        for it in items:
            if "label_name" not in it and "label" in it:
                it["label_name"] = ID_TO_LABEL.get(it["label"], str(it["label"]))
        all_items.extend(items)

    if not all_items:
        print("  (no records found)")
        return None

    counter = Counter(it.get("label_name", "UNKNOWN") for it in all_items)
    print(f"\nLoaded {len(all_items):,} records")
    print("Label distribution:")
    print(fmt_distribution(counter))

    samples_by_class: dict[str, list[dict]] = defaultdict(list)
    for it in all_items:
        name = it.get("label_name", "UNKNOWN")
        if len(samples_by_class[name]) < samples_per_class:
            samples_by_class[name].append(it)

    md: list[str] = []
    md.append(f"# {dataset_name} — processed JSONL view\n")
    md.append("Files included:\n")
    for fp in files:
        md.append(f"- `{fp}`")
    md.append(f"\nRecords loaded: **{len(all_items):,}**\n")
    md.append("## Label distribution\n```\n" + fmt_distribution(counter) + "\n```\n")

    md.append("## Sample records per class\n")
    md.append("Each record is exactly what the classifier sees during "
              "training: a `text` field (a chunk of log lines) plus an "
              "integer `label`.\n")
    for sev in ("FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"):
        md.append(f"### Label = `{sev}`  (id={LABEL_MAP[sev]})\n")
        examples = samples_by_class.get(sev, [])
        if not examples:
            md.append("_no examples in this slice of the data_\n")
            continue
        for i, it in enumerate(examples, 1):
            extras = {k: v for k, v in it.items()
                      if k not in {"text", "label", "label_name"}}
            extras_str = f"  _meta: `{extras}`_" if extras else ""
            md.append(f"**Example {i}**{extras_str}\n")
            md.append("```text")
            md.append(short(it.get("text", ""), 600))
            md.append("```\n")

    print("\nSample records per class (first example only, truncated):")
    for sev in ("FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"):
        ex = samples_by_class.get(sev, [])
        if ex:
            print(f"\n  [{sev}]  -> id={LABEL_MAP[sev]}")
            print(textwrap.indent(short(ex[0].get("text", ""), 240), "      "))
        else:
            print(f"\n  [{sev}]  -> id={LABEL_MAP[sev]}  (no examples)")

    report = "\n".join(md) + "\n"
    out_path = out_dir / out_filename
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote {repo_rel(out_path)}")
    return report


# ---------------------------------------------------------------------------
# 3. Inline demo (used when no data is found anywhere)
# ---------------------------------------------------------------------------

DEMO_BGL_LINES = """\
- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
- 1117838571 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.51.601412 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
KERNDTLB 1117841234 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.55.30.121111 R02-M1-N0-C:J12-U11 RAS KERNEL INFO data TLB error interrupt
- 1117842111 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-16.10.10.555000 R02-M1-N0-C:J12-U11 RAS KERNEL WARNING ddr: Unable to steer
- 1117842500 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-16.15.00.999000 R02-M1-N0-C:J12-U11 RAS KERNEL ERROR rts panic! - stopping execution
- 1117842600 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-16.20.00.000000 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL machine check interrupt (bit=0x32)
"""


def run_inline_demo(samples_per_class: int, out_dir: Path) -> None:
    print(banner("Inline demo (no real data found on disk)"))
    print("No BGL.log, processed JSONL or synthetic JSONL was found "
          "in the default locations.\nShowing how labelling works on a "
          "tiny built-in sample so you still get an idea of the output.\n")

    parsed: list[tuple[str, str]] = []
    for line in DEMO_BGL_LINES.strip().splitlines():
        sev, text = classify_bgl_line(line)
        parsed.append((sev, text))

    for sev, text in parsed:
        print(f"  [{sev:<18}]  {short(text, 120)}")

    md = ["# Inline demo (no real data found)\n",
          "These lines are hard-coded inside the script so you can still "
          "see what the labelling rule produces from a raw BGL-style "
          "line.\n",
          "| Extracted label | Raw line (truncated) |",
          "|---|---|"]
    for sev, text in parsed:
        md.append(f"| `{sev}` | `{short(text, 160)}` |")

    out_path = out_dir / "inline_demo_sample.md"
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nWrote {repo_rel(out_path)}")


# ---------------------------------------------------------------------------
# Glue
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bgl-raw", type=Path, default=None,
                        help="Path to raw BGL.log file.")
    parser.add_argument("--bgl-processed-dir", type=Path, default=None,
                        help="Dir containing bgl_train.jsonl / bgl_val.jsonl / bgl_test.jsonl.")
    parser.add_argument("--synthetic-dir", type=Path, default=None,
                        help="Dir containing synthetic *.jsonl files.")
    parser.add_argument("--samples-per-class", type=int, default=2,
                        help="How many labelled samples to show per class. Default: 2.")
    parser.add_argument("--max-raw-lines", type=int, default=200_000,
                        help="Cap on how many raw BGL.log lines to parse. Default: 200,000.")
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "helpful_scripts" / "samples",
                        help="Where to write sample .md files. Default: helpful_scripts/samples/")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(banner("Log Severity Classifier — Dataset & Label Visualizer"))
    print("Class taxonomy (4 labels):")
    for name, idx in LABEL_MAP.items():
        print(f"  {idx} = {name}")
    print(f"\nOutput dir: {repo_rel(out_dir)}/")

    produced_anything = False
    summary_links: list[tuple[str, str]] = []

    # ---- BGL raw ----
    bgl_raw = args.bgl_raw or first_existing(BGL_RAW_CANDIDATES)
    if bgl_raw and bgl_raw.exists():
        visualize_bgl_raw(bgl_raw, args.max_raw_lines, args.samples_per_class, out_dir)
        produced_anything = True
        summary_links.append(("BGL (raw lines + chunks)", "bgl_raw_sample.md"))
    else:
        print(banner("BGL — raw lines"))
        print("No raw BGL.log found. Looked in:")
        for p in BGL_RAW_CANDIDATES:
            print(f"  - {p}")
        print("Pass --bgl-raw /path/to/BGL.log to enable this section.")
        print("(Download: https://zenodo.org/records/8196385 -> BGL.zip)")

    # ---- BGL processed JSONL ----
    bgl_proc_dir = args.bgl_processed_dir or first_existing(BGL_PROCESSED_CANDIDATES)
    if bgl_proc_dir and bgl_proc_dir.exists():
        bgl_files = sorted(bgl_proc_dir.glob("bgl_*.jsonl"))
        if bgl_files:
            visualize_jsonl_dataset(
                "BGL", bgl_files, args.samples_per_class, out_dir,
                out_filename="bgl_processed_sample.md",
            )
            produced_anything = True
            summary_links.append(("BGL (processed JSONL)", "bgl_processed_sample.md"))
        else:
            print(banner("BGL — processed JSONL"))
            print(f"Found dir {bgl_proc_dir} but no bgl_*.jsonl inside.")
    else:
        print(banner("BGL — processed JSONL"))
        print("No processed BGL dir found. Looked in:")
        for p in BGL_PROCESSED_CANDIDATES:
            print(f"  - {p}")
        print("Pass --bgl-processed-dir /path/to/dir to enable this section.")

    # ---- Synthetic ----
    syn_dir = args.synthetic_dir or first_existing(SYNTHETIC_CANDIDATES)
    if syn_dir and syn_dir.exists():
        syn_files = sorted(p for p in syn_dir.rglob("*.jsonl"))
        if syn_files:
            visualize_jsonl_dataset(
                "Synthetic", syn_files, args.samples_per_class, out_dir,
                out_filename="synthetic_sample.md",
            )
            produced_anything = True
            summary_links.append(("Synthetic (JSONL)", "synthetic_sample.md"))
        else:
            print(banner("Synthetic — JSONL"))
            print(f"Found dir {syn_dir} but no *.jsonl inside.")
    else:
        print(banner("Synthetic — JSONL"))
        print("No synthetic dir found. Looked in:")
        for p in SYNTHETIC_CANDIDATES:
            print(f"  - {p}")
        print("Pass --synthetic-dir /path/to/dir to enable this section.")

    # ---- Fallback inline demo ----
    if not produced_anything:
        run_inline_demo(args.samples_per_class, out_dir)
        summary_links.append(("Inline demo (no real data)", "inline_demo_sample.md"))

    # ---- SUMMARY.md ----
    summary = ["# Visualizer output summary\n",
               "This folder contains labelled samples for each dataset used by "
               "the log severity classifier. Open any of the files below to "
               "see how the raw data maps to one of the 4 class labels "
               "(FATAL_OR_CRITICAL / ERROR / WARNING / NORMAL).\n",
               "## Class taxonomy\n",
               "| id | label | meaning |",
               "|---|---|---|",
               "| 0 | FATAL_OR_CRITICAL | system crash, unrecoverable error |",
               "| 1 | ERROR | recoverable error, exception, 5xx |",
               "| 2 | WARNING | degradation signal, latency, retry |",
               "| 3 | NORMAL | only INFO/DEBUG/TRACE, nothing anomalous |\n",
               "## Generated files\n"]
    for title, fname in summary_links:
        summary.append(f"- **{title}** — [`{fname}`](./{fname})")
    (out_dir / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(banner("Done"))
    print(f"Summary index: {repo_rel(out_dir / 'SUMMARY.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
