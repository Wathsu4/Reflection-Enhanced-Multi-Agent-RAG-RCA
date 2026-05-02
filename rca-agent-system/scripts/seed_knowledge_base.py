"""Seed (or re-seed) ChromaDB from markdown files in seed/incidents/.

Idempotent: running this twice does not duplicate records, because we
upsert by `incident_id`. Safe to run on every deploy.

Usage:
    uv run python scripts/seed_knowledge_base.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Allow running this script directly (`python scripts/seed_...`) without
# `uv run` having to set PYTHONPATH explicitly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.memory.chroma_store import IncidentMemory, IncidentRecord  # noqa: E402

SEED_DIR = PROJECT_ROOT / "seed" / "incidents"

# Required keys in the YAML frontmatter; surfacing errors loudly here
# saves a lot of debugging later when retrieval misbehaves due to
# silently-missing metadata.
REQUIRED_FIELDS = {
    "incident_id",
    "title",
    "severity",
    "root_cause",
    "resolution",
    "tags",
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_markdown(path: Path) -> tuple[dict, str]:
    """Split a `*.md` file into (frontmatter dict, body text).

    Raises `ValueError` if the file doesn't begin with a YAML frontmatter
    block, or is missing any of the required fields.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(
            f"{path.name}: missing or malformed YAML frontmatter "
            "(expected a `---` block at the top of the file)"
        )

    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path.name}: frontmatter is not a mapping")

    missing = REQUIRED_FIELDS - meta.keys()
    if missing:
        raise ValueError(
            f"{path.name}: frontmatter is missing fields: {sorted(missing)}"
        )

    body = match.group(2).strip()
    return meta, body


def build_record(meta: dict) -> IncidentRecord:
    """Map raw frontmatter to a typed `IncidentRecord`."""
    return IncidentRecord(
        incident_id=str(meta["incident_id"]),
        title=str(meta["title"]),
        severity=str(meta["severity"]),
        root_cause=str(meta["root_cause"]),
        resolution=str(meta["resolution"]),
        tags=str(meta["tags"]),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=SEED_DIR,
        help="Directory containing *.md seed files (default: seed/incidents/)",
    )
    args = parser.parse_args(argv)

    if not args.seed_dir.is_dir():
        print(f"error: seed dir does not exist: {args.seed_dir}", file=sys.stderr)
        return 2

    memory = IncidentMemory()
    files = sorted(args.seed_dir.glob("*.md"))
    if not files:
        print(f"warning: no *.md files in {args.seed_dir}", file=sys.stderr)
        return 1

    seeded = 0
    for path in files:
        meta, body = parse_markdown(path)
        record = build_record(meta)
        # Embed the structured summary plus the markdown body, so
        # retrieval can match either the curated fields or any
        # idiosyncratic phrasing in the narrative.
        doc_text = record.to_document() + "\n\n" + body
        memory.add(record, document_text=doc_text)
        seeded += 1
        print(f"  + {record.incident_id} ({path.name})")

    total = memory.count()
    print(f"\nSeeded {seeded} incident(s). Collection now contains {total} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
