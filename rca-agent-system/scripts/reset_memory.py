"""Wipe the ChromaDB knowledge base and re-seed it from `seed/incidents/`.

Useful before a demo, between evaluation runs, or whenever score drift
from previous reflection cycles needs to be cleared.

Usage:
    uv run python scripts/reset_memory.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from chromadb.api.client import SharedSystemClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.settings import settings  # noqa: E402
from scripts import seed_knowledge_base  # noqa: E402


def reset_memory(persist_dir: Path | None = None) -> int:
    """Remove the on-disk Chroma directory and re-seed.

    Returns the seeder's exit code (0 on success). Importable from
    tests so we don't have to spawn a subprocess.
    """
    target = Path(persist_dir) if persist_dir else Path(settings.chroma_persist_dir)
    if target.exists():
        # chromadb 1.x keeps the persistent client (and its sqlite
        # handles) in a process-wide cache. If we rmtree without first
        # dropping the cache, the next `IncidentMemory()` call will
        # come back from cache pointing at the now-deleted database
        # and writes will fail with "readonly database". Clear it.
        SharedSystemClient.clear_system_cache()
        shutil.rmtree(target)
        print(f"removed {target}")
    else:
        print(f"(no existing {target})")

    return seed_knowledge_base.main([])


if __name__ == "__main__":
    raise SystemExit(reset_memory())
