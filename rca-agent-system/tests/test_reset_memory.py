"""Tests for `scripts/reset_memory.py`.

The reset script is the demo / evaluation safety valve: when the
dynamic memory drifts during testing, this restores known-good state.
The contract we care about is:

  * Pre-existing on-disk state in the chroma dir is removed.
  * After reset, the seeder runs successfully and the collection has
    exactly the seed count.
  * Pre-reset adjustments (e.g. boosted success_scores) are gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rca_system.memory.chroma_store import IncidentMemory, IncidentRecord
from scripts import reset_memory as reset_module
from scripts import seed_knowledge_base as seeder
from tests._fake_embed import FakeEmbeddingFunction

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_SEED_DIR = PROJECT_ROOT / "seed" / "incidents"


@pytest.fixture
def patched_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Wire both the reset script and the seeder to a tmp chroma dir
    using the fake embedding function -- no model download, no
    interference with the prod data dir."""
    persist_dir = tmp_path / "chroma"

    def make_mem() -> IncidentMemory:
        return IncidentMemory(
            persist_dir=persist_dir,
            collection_name="incident_memory_test",
            embedding_function=FakeEmbeddingFunction(),
        )

    # Both scripts call `IncidentMemory()` with no args; redirect both.
    monkeypatch.setattr(seeder, "IncidentMemory", make_mem)
    monkeypatch.setattr(
        reset_module.settings, "chroma_persist_dir", str(persist_dir)
    )
    return persist_dir


def test_reset_removes_existing_dir_and_reseeds(
    patched_pipeline: Path,
) -> None:
    persist_dir = patched_pipeline

    # Prime: seed once, then mutate a score so we can detect that the
    # reset really wiped state (not just left scores at 1.0 by accident).
    seeder.main([])
    mem = IncidentMemory(
        persist_dir=persist_dir,
        collection_name="incident_memory_test",
        embedding_function=FakeEmbeddingFunction(),
    )
    boosted_id = "redis-conn-refused-001"
    # Tier 0 Phase 2: delta=0.5 is re-clamped to 0.2 (max), giving a 1.0
    # pseudocount -> from the fresh seed prior (alpha=beta=2.0):
    # alpha=3.0, beta=2.0 -> success_score = 2*3/(3+2) = 1.2 (not 1.5).
    mem.update_score(boosted_id, 0.5)
    # Direct by-id lookup, not a similarity `.query()` -- Tier 0 Phase 5
    # grew the seed set past a fixed `k`, so a top-k similarity search
    # over the fake (arbitrary, hash-based) embeddings can no longer be
    # relied on to include every record, including this one.
    pre_meta = mem._collection.get(  # noqa: SLF001 -- intentional internal check
        ids=[boosted_id], include=["metadatas"]
    )["metadatas"][0]
    assert pre_meta["success_score"] == pytest.approx(1.2)
    del mem  # close any in-process handles before rmtree

    # Act: reset
    rc = reset_module.reset_memory(persist_dir=persist_dir)
    assert rc == 0

    # Assert: directory exists, has the seed count, and scores are all 1.0
    fresh = IncidentMemory(
        persist_dir=persist_dir,
        collection_name="incident_memory_test",
        embedding_function=FakeEmbeddingFunction(),
    )
    expected_count = len(list(SHIPPED_SEED_DIR.glob("*.md")))
    assert fresh.count() == expected_count

    # Full sweep via a direct (non-similarity) `.get()` so every seeded
    # record is checked regardless of how large the seed set grows.
    post_reset = fresh._collection.get(include=["metadatas"])  # noqa: SLF001
    for incident_id, meta in zip(post_reset["ids"], post_reset["metadatas"]):
        assert meta["success_score"] == pytest.approx(1.0), (
            f"After reset, {incident_id} still has score "
            f"{meta['success_score']} (expected 1.0)"
        )


def test_reset_handles_missing_dir(patched_pipeline: Path) -> None:
    """If the chroma dir doesn't exist yet, the reset must still
    succeed by creating + seeding fresh."""
    persist_dir = patched_pipeline
    assert not persist_dir.exists()  # fresh tmp_path

    rc = reset_module.reset_memory(persist_dir=persist_dir)
    assert rc == 0

    fresh = IncidentMemory(
        persist_dir=persist_dir,
        collection_name="incident_memory_test",
        embedding_function=FakeEmbeddingFunction(),
    )
    expected_count = len(list(SHIPPED_SEED_DIR.glob("*.md")))
    assert fresh.count() == expected_count
