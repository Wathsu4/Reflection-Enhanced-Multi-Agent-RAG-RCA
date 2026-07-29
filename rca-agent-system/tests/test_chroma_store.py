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


def _meta(mem: IncidentMemory, incident_id: str) -> dict:
    """Direct by-id metadata lookup, bypassing similarity search -- used
    where multiple records share an embedding (identical `to_document()`
    text) and `query()`'s top-1 result would be ambiguous."""
    res = mem._collection.get(ids=[incident_id], include=["metadatas"])  # noqa: SLF001
    return dict(res["metadatas"][0])


def test_update_score_seeded_fresh_is_exactly_neutral(tmp_path: Path) -> None:
    """Pins the "prior is neutral" invariant: a record constructed
    without an explicit success_score derives it from alpha == beta ==
    score_prior_strength, giving exactly 1.0 -- matching the pre-Phase-2
    default."""
    mem = make_memory(tmp_path)
    record = make_record("fresh-001")
    assert record.alpha == record.beta == 2.0  # default score_prior_strength
    assert record.success_score == pytest.approx(1.0)
    mem.add(record)
    assert _meta(mem, "fresh-001")["success_score"] == pytest.approx(1.0)


def test_update_score_single_extreme_call_moves_by_bounded_amount(
    tmp_path: Path,
) -> None:
    """Tier 0 Phase 2: even a wildly out-of-range delta can't swing the
    score straight to an extreme in one call -- it's re-clamped to
    +-0.2, converted to at most a 1.0 pseudo-count, and applied against
    the existing alpha/beta prior (default alpha=beta=2.0).

      delta=10.0  -> clamped to  0.2 -> pseudocount=1.0 -> alpha=3, beta=2
                  -> success_score = 2*3/(3+2) = 1.2 (NOT 2.0)
      delta=-99.0 -> clamped to -0.2 -> pseudocount=1.0 -> alpha=2, beta=3
                  -> success_score = 2*2/(2+3) = 0.8 (NOT 0.0)
    """
    mem = make_memory(tmp_path)
    mem.add(make_record("clamp-high"))
    mem.add(make_record("clamp-low"))

    mem.update_score("clamp-high", delta=10.0)
    assert _meta(mem, "clamp-high")["success_score"] == pytest.approx(1.2)
    assert _meta(mem, "clamp-high")["alpha"] == pytest.approx(3.0)
    assert _meta(mem, "clamp-high")["beta"] == pytest.approx(2.0)

    mem.update_score("clamp-low", delta=-99.0)
    assert _meta(mem, "clamp-low")["success_score"] == pytest.approx(0.8)
    assert _meta(mem, "clamp-low")["alpha"] == pytest.approx(2.0)
    assert _meta(mem, "clamp-low")["beta"] == pytest.approx(3.0)


def test_update_score_repeated_extreme_calls_eventually_saturate(
    tmp_path: Path,
) -> None:
    """The "runaway reputation" defense (docs/DEFENSE_GUIDE.md) still
    holds under the pseudo-count model: sustained one-sided pressure
    keeps pushing the score toward the bound, it just takes more calls
    than a single one now. After N=50 max-magnitude positive calls from
    the default prior (alpha=beta=2.0), each adding a full 1.0
    pseudocount to alpha:
        alpha = 2 + 50*1.0 = 52, beta = 2 (unchanged)
        success_score = 2*52/(52+2) = 104/54 = 1.9259259...
    -- much closer to 2.0 than a single call (1.2), strictly below it,
    and monotonically non-decreasing at every step (never overshoots).
    The negative direction is exactly symmetric.
    """
    mem = make_memory(tmp_path)
    mem.add(make_record("saturate-high"))
    mem.add(make_record("saturate-low"))

    prev_high = 1.0
    prev_low = 1.0
    for _ in range(50):
        mem.update_score("saturate-high", delta=10.0)
        mem.update_score("saturate-low", delta=-99.0)
        high = _meta(mem, "saturate-high")["success_score"]
        low = _meta(mem, "saturate-low")["success_score"]
        assert prev_high <= high < 2.0
        assert 0.0 < low <= prev_low
        prev_high, prev_low = high, low

    assert _meta(mem, "saturate-high")["success_score"] == pytest.approx(104 / 54)
    assert _meta(mem, "saturate-low")["success_score"] == pytest.approx(4 / 54)


def test_update_score_handles_pre_phase2_metadata_missing_alpha_beta(
    tmp_path: Path,
) -> None:
    """Migration adversarial case: a record written before Tier 0 Phase 2
    (no `alpha`/`beta` in its stored metadata at all -- the documented
    "not backfilled" scenario, TIER0_PLAN.md SS4). `update_score` must not
    crash; it falls back to `settings.score_prior_strength` for the
    missing fields, same as a fresh record."""
    mem = make_memory(tmp_path)
    mem.add(make_record("legacy-001"))
    # Simulate stale on-disk metadata by stripping alpha/beta directly,
    # bypassing IncidentRecord (which always includes them).
    stale_meta = _meta(mem, "legacy-001")
    del stale_meta["alpha"]
    del stale_meta["beta"]
    mem._collection.update(ids=["legacy-001"], metadatas=[stale_meta])  # noqa: SLF001

    mem.update_score("legacy-001", delta=0.1)  # must not raise

    meta = _meta(mem, "legacy-001")
    # Falls back to the default prior (2.0/2.0) before applying the delta.
    assert meta["alpha"] == pytest.approx(2.5)
    assert meta["beta"] == pytest.approx(2.0)
    assert meta["success_score"] == pytest.approx(10 / 9)


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


def test_mark_retrieved_does_not_touch_alpha_beta(tmp_path: Path) -> None:
    """`usage_count` (retrieval popularity) and `alpha`/`beta` (reflection
    confidence) are independent counters -- retrieval must never bump
    the score prior, and score updates must never bump usage_count."""
    mem = make_memory(tmp_path)
    mem.add(make_record("independent-001"))

    mem.mark_retrieved(["independent-001"])
    mem.mark_retrieved(["independent-001"])
    meta = _meta(mem, "independent-001")
    assert meta["usage_count"] == 2
    assert meta["alpha"] == pytest.approx(2.0)
    assert meta["beta"] == pytest.approx(2.0)

    mem.update_score("independent-001", delta=0.2)
    meta = _meta(mem, "independent-001")
    assert meta["usage_count"] == 2  # unchanged by a score update
    assert meta["alpha"] == pytest.approx(3.0)


def test_mark_retrieved_empty_list_is_noop(tmp_path: Path) -> None:
    mem = make_memory(tmp_path)
    mem.mark_retrieved([])  # should not raise even on empty collection
