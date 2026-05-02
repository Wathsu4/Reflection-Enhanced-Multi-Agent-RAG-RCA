"""Tests for `apply_reflection_to_memory`.

This is the only place in the system where success_score gets mutated
post-seed. We verify:
  * old/new/delta are reported correctly per id.
  * Unknown ids are silently skipped (no exception).
  * Per-call clamping interacts cleanly with the cumulative bound on
    `success_score` (kept in [0, 2] by IncidentMemory).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rca_system.memory.chroma_store import IncidentMemory, IncidentRecord
from rca_system.tools import update_memory as um_module
from tests._fake_embed import FakeEmbeddingFunction


@pytest.fixture
def memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> IncidentMemory:
    mem = IncidentMemory(
        persist_dir=tmp_path / "chroma",
        collection_name="incident_memory_test",
        embedding_function=FakeEmbeddingFunction(),
    )
    monkeypatch.setattr(um_module, "_memory", mem)
    return mem


def make_record(incident_id: str, score: float = 1.0) -> IncidentRecord:
    return IncidentRecord(
        incident_id=incident_id,
        title="t",
        severity="ERROR",
        root_cause="rc",
        resolution="r",
        tags="t",
        success_score=score,
    )


# ---------- happy path ----------


def test_returns_old_new_delta_per_id(memory: IncidentMemory) -> None:
    memory.add(make_record("a", score=1.0))
    memory.add(make_record("b", score=1.0))

    out = um_module.apply_reflection_to_memory({"a": 0.1, "b": -0.05})
    assert "updated" in out
    assert out["updated"]["a"]["old_score"] == 1.0
    assert out["updated"]["a"]["new_score"] == pytest.approx(1.1)
    assert out["updated"]["a"]["delta"] == 0.1
    assert out["updated"]["b"]["new_score"] == pytest.approx(0.95)


def test_persists_new_score_to_memory(memory: IncidentMemory) -> None:
    """The whole point of this tool is that scores survive the call."""
    memory.add(make_record("persist-001", score=1.0))
    um_module.apply_reflection_to_memory({"persist-001": 0.2})

    # Re-query memory directly to make sure the score really stuck.
    hit = memory.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(1.2)


# ---------- robustness ----------


def test_unknown_id_is_silently_skipped(memory: IncidentMemory) -> None:
    """The reflection agent sometimes references stale ids. We must
    not raise -- the rest of the batch should still apply."""
    memory.add(make_record("known-001", score=1.0))
    out = um_module.apply_reflection_to_memory(
        {"known-001": 0.1, "ghost-001": 0.1}
    )
    assert "known-001" in out["updated"]
    assert "ghost-001" not in out["updated"]


def test_non_numeric_delta_is_skipped(memory: IncidentMemory) -> None:
    memory.add(make_record("a"))
    out = um_module.apply_reflection_to_memory({"a": "not a number"})  # type: ignore[arg-type]
    assert out["updated"] == {}


def test_garbage_argument_returns_empty_updated(
    memory: IncidentMemory,
) -> None:
    out = um_module.apply_reflection_to_memory("nope")  # type: ignore[arg-type]
    assert out == {"updated": {}}


# ---------- clamping interaction with the cumulative score bound ----------


def test_repeated_positive_deltas_clamp_at_2(memory: IncidentMemory) -> None:
    """Even if reflection keeps boosting an incident every run, the
    score can't run away past 2.0 -- IncidentMemory.update_score
    enforces that cap."""
    memory.add(make_record("clamped-001", score=1.9))
    um_module.apply_reflection_to_memory({"clamped-001": 0.2})
    um_module.apply_reflection_to_memory({"clamped-001": 0.2})
    um_module.apply_reflection_to_memory({"clamped-001": 0.2})

    hit = memory.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(2.0)


def test_repeated_negative_deltas_clamp_at_0(memory: IncidentMemory) -> None:
    memory.add(make_record("demoted-001", score=0.1))
    um_module.apply_reflection_to_memory({"demoted-001": -0.2})
    um_module.apply_reflection_to_memory({"demoted-001": -0.2})

    hit = memory.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(0.0)
