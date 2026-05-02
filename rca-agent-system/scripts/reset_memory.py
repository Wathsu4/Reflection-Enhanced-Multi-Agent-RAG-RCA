"""Wipe the ChromaDB knowledge base and re-seed it from `seed/incidents/`.

Useful before a demo, between evaluation runs, or whenever score drift
from previous reflection cycles needs to be cleared.

Usage:
    uv run python scripts/reset_memory.py
"""

from __future__ import annotations

import gc
import shutil
import sys
import time
from pathlib import Path

from chromadb.api.client import SharedSystemClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rca_system.settings import settings  # noqa: E402
from scripts import seed_knowledge_base  # noqa: E402


def _rmtree_with_retries(target: Path, attempts: int = 5) -> None:
    """`shutil.rmtree` with retry-and-backoff for Windows.

    chromadb's HNSW index file (`data_level0.bin`) is memory-mapped.
    On Windows, you cannot unlink a file with an open mmap handle;
    on POSIX the inode persists until the mapping releases. Even
    after `SharedSystemClient.clear_system_cache()` drops the cached
    client refs, the underlying System / Segment objects can take a
    GC cycle (or briefly longer on Windows) to release the mmap.

    Force GC then retry with linear backoff. ~1.5s worst case.
    """
    last_err: OSError | None = None
    for i in range(attempts):
        try:
            shutil.rmtree(target)
            return
        except PermissionError as exc:
            last_err = exc
            gc.collect()
            time.sleep(0.1 * (i + 1))
    if last_err is not None:
        raise last_err


def reset_memory(persist_dir: Path | None = None) -> int:
    """Remove the on-disk Chroma directory and re-seed.

    Returns the seeder's exit code (0 on success). Importable from
    tests so we don't have to spawn a subprocess.
    """
    target = Path(persist_dir) if persist_dir else Path(settings.chroma_persist_dir)
    if target.exists():
        # chromadb 1.x keeps the persistent client (and its sqlite
        # + mmap handles) in a process-wide cache. If we rmtree
        # without first dropping the cache, two things go wrong:
        #   1. POSIX: the next `IncidentMemory()` call comes back
        #      from cache pointing at the deleted database; writes
        #      fail with "readonly database".
        #   2. Windows: rmtree itself fails with WinError 32 because
        #      the mmap'd HNSW index file is still open.
        # Both are addressed by clear_system_cache + gc + retry.
        SharedSystemClient.clear_system_cache()
        gc.collect()
        _rmtree_with_retries(target)
        print(f"removed {target}")
    else:
        print(f"(no existing {target})")

    return seed_knowledge_base.main([])


if __name__ == "__main__":
    raise SystemExit(reset_memory())
