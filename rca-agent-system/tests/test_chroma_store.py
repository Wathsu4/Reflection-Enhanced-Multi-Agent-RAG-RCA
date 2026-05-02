"""Unit tests for `IncidentMemory`.

We use a fake embedding function and a per-test tmp directory so the
tests are fast (no model download) and isolated (each test gets a
fresh on-disk index).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from rca_system.memory.chroma_store import IncidentMemory, IncidentRecord
from tests._fake_embed import FakeEmbeddingFunction


def make_memory(tmp_path: Path) -> IncidentMemory:
    return IncidentMemory(
        persist_dir=tmp_path / "chroma",
        collection_name="incident_memory_test",
        embedding_function=FakeEmbeddingFunction(),
    )


def make_record(incident_id: str = "test-001", **overrides) -> IncidentRecord:
    fields = {
        "incident_id": incident_id,
        "title": "Test incident",
        "severity": "ERROR",
        "root_cause": "Something broke",
        "resolution": "It was fixed",
        "tags": "test,unit",
    }
    fields.update(overrides)
    return IncidentRecord(**fields)


# ---------- IncidentRecord.to_document ----------


def test_to_document_includes_all_summary_fields() -> None:
    """The embedded text must contain the structured fields so retrieval
    can match on title/severity/root_cause keywords directly."""
    record = make_record(
        title="Redis connection refused",
        severity="ERROR",
        root_cause="Firewall rule",
        tags="redis,network",
    )
    doc = record.to_document()
    for needle in ("Redis connection refused", "ERROR", "Firewall rule", "redis,network"):
        assert needle in doc


# ---------- add / count / idempotency ----------


def test_add_inserts_record(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    mem.add(make_record())
    assert mem.count() == 1


def test_add_is_idempotent_on_id(tmp_path: Path) -> None:
    """Re-adding the same id must not duplicate. This is the property
    the seeder script relies on for safe re-runs."""
    mem = make_memory(tmp_path)
    mem.add(make_record(incident_id="dup-001"))
    mem.add(make_record(incident_id="dup-001", title="Updated title"))
    assert mem.count() == 1


def test_add_stamps_added_ts_when_zero(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    record = make_record()
    assert record.added_ts == 0.0
    before = time.time()
    mem.add(record)
    assert before <= record.added_ts <= time.time() + 1


# ---------- query ----------


def test_query_returns_hits_with_required_keys(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    mem.add(make_record("a"))
    mem.add(make_record("b"))

    hits = mem.query("anything", k=2)
    assert len(hits) == 2
    for hit in hits:
        # Contract verified by the retrieve_incidents tool downstream.
        assert {"incident_id", "document", "metadata", "distance", "similarity"} <= hit.keys()
        assert isinstance(hit["similarity"], float)
        # Cosine similarity is in [-1, 1]; for normalised hash vectors
        # it'll typically be > 0 but we don't want to rely on that.
        assert -1.0 <= hit["similarity"] <= 1.0


def test_query_respects_k(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    for i in range(5):
        mem.add(make_record(f"r-{i}"))
    assert len(mem.query("foo", k=3)) == 3


def test_query_on_empty_collection_returns_empty(tmp_path: Path) -> None:
    """No results, no exceptions."""
    mem = make_memory(tmp_path)
    assert mem.query("anything", k=5) == []


# ---------- update_score ----------


def test_update_score_clamps_to_range(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    mem.add(make_record("clamp-001"))
    # Push way over the upper bound -- must clamp at 2.0.
    mem.update_score("clamp-001", delta=10.0)
    hit = mem.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(2.0)

    # Push way below 0 -- must clamp at 0.0.
    mem.update_score("clamp-001", delta=-99.0)
    hit = mem.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(0.0)


def test_update_score_unknown_id_is_noop(tmp_path: Path) -> None:
    """Update on a missing id must not raise -- the reflection agent
    can pass stale ids when memory is concurrently modified."""
    mem = make_memory(tmp_path)
    mem.update_score("does-not-exist", delta=0.5)  # should not raise


# ---------- mark_retrieved ----------


def test_mark_retrieved_increments_usage_count(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    mem.add(make_record("usage-001"))
    mem.mark_retrieved(["usage-001"])
    mem.mark_retrieved(["usage-001"])

    hit = mem.query("anything", k=1)[0]
    assert hit["metadata"]["usage_count"] == 2
    assert hit["metadata"]["last_used_ts"] > 0


def test_mark_retrieved_empty_list_is_noop(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    mem.mark_retrieved([])  # should not raise even on empty collection
