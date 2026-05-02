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
    mem.update_score(boosted_id, 0.5)
    pre_reset = mem.query("anything", k=10)
    pre_score = next(
        h["metadata"]["success_score"]
        for h in pre_reset
        if h["incident_id"] == boosted_id
    )
    assert pre_score == pytest.approx(1.5)
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

    post_reset = fresh.query("anything", k=10)
    for hit in post_reset:
        assert hit["metadata"]["success_score"] == pytest.approx(1.0), (
            f"After reset, {hit['incident_id']} still has score "
            f"{hit['metadata']['success_score']} (expected 1.0)"
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
