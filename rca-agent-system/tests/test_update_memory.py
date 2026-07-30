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
    """Tier 0 Phase 2 arithmetic (default prior alpha=beta=2.0):
      a: delta=0.1  -> pseudocount=0.1/0.2=0.5  -> alpha=2.5, beta=2.0
         -> new_score = 2*2.5/(2.5+2.0) = 5/4.5 = 10/9 = 1.1111...
      b: delta=-0.05 -> pseudocount=0.05/0.2=0.25 -> alpha=2.0, beta=2.25
         -> new_score = 2*2.0/(2.0+2.25) = 4/4.25 = 16/17 = 0.9411...
    (No longer simple addition -- see IncidentMemory.update_score.)
    """
    memory.add(make_record("a", score=1.0))
    memory.add(make_record("b", score=1.0))

    out = um_module.apply_reflection_to_memory({"a": 0.1, "b": -0.05})
    assert "updated" in out
    assert out["updated"]["a"]["old_score"] == 1.0
    # apply_reflection_to_memory rounds its reported scores to 3dp.
    assert out["updated"]["a"]["new_score"] == pytest.approx(round(10 / 9, 3))
    assert out["updated"]["a"]["delta"] == 0.1
    assert out["updated"]["b"]["new_score"] == pytest.approx(round(16 / 17, 3))


def test_persists_new_score_to_memory(memory: IncidentMemory) -> None:
    """The whole point of this tool is that scores survive the call.

    delta=0.2 is the max-magnitude delta, so pseudocount=0.2/0.2=1.0
    exactly -> alpha=2.0+1.0=3.0, beta=2.0 (unchanged) -> new_score =
    2*3/(3+2) = 6/5 = 1.2. This happens to match the old linear-add
    result (1.0+0.2) at this specific starting point and delta size --
    coincidence of a fresh prior + a max-magnitude single call, not
    evidence the formula is unchanged (see the non-max-delta case in
    test_returns_old_new_delta_per_id above, which does differ).
    """
    memory.add(make_record("persist-001", score=1.0))
    um_module.apply_reflection_to_memory({"persist-001": 0.2})

    # Re-query memory directly to make sure the score really stuck.
    hit = memory.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(1.2)


# ---------- robustness ----------


def test_unknown_id_is_skipped_but_reported(memory: IncidentMemory) -> None:
    """The reflection agent sometimes references stale ids. We must
    not raise -- the rest of the batch should still apply, and the
    skipped id must be reported rather than swallowed."""
    memory.add(make_record("known-001", score=1.0))
    out = um_module.apply_reflection_to_memory(
        {"known-001": 0.1, "ghost-001": 0.1}
    )
    assert "known-001" in out["updated"]
    assert "ghost-001" not in out["updated"]
    assert out["skipped"] == {"ghost-001": "unknown_incident"}


def test_non_numeric_delta_is_skipped(memory: IncidentMemory) -> None:
    memory.add(make_record("a"))
    out = um_module.apply_reflection_to_memory({"a": "not a number"})  # type: ignore[arg-type]
    assert out["updated"] == {}
    assert out["skipped"] == {"a": "invalid_delta"}


def test_garbage_argument_returns_empty_updated(
    memory: IncidentMemory,
) -> None:
    out = um_module.apply_reflection_to_memory("nope")  # type: ignore[arg-type]
    assert out == {"updated": {}, "skipped": {}}


# ---------- clamping interaction with the cumulative score bound ----------


def test_repeated_positive_deltas_approach_but_never_reach_2(
    memory: IncidentMemory,
) -> None:
    """Tier 0 Phase 2 intentionally changes this from "reaches the 2.0
    clamp in 1-2 calls" to "asymptotically approaches 2.0" -- no single
    run (or handful of runs) can swing a score straight to an extreme
    (see TIER0_PLAN.md SS3 Round 2 log). Sustained one-sided pressure
    still gets there eventually: this is not a loosened cap, just a
    slower, stickier one.

    Starting fresh (alpha=beta=2.0), 100 repeated max-magnitude (+0.2)
    calls each add a full 1.0 pseudocount to alpha:
        alpha = 2 + 100*1.0 = 102, beta = 2 (unchanged)
        success_score = 2*102/(102+2) = 204/104 = 51/26 = 1.9615...
    -- clearly trending toward 2.0, but strictly below it.
    """
    memory.add(make_record("clamped-001"))  # fresh: alpha=beta=2.0
    for _ in range(100):
        out = um_module.apply_reflection_to_memory({"clamped-001": 0.2})
    assert out["updated"]["clamped-001"]["new_score"] < 2.0

    hit = memory.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(51 / 26)
    assert hit["metadata"]["success_score"] < 2.0


def test_repeated_negative_deltas_approach_but_never_reach_0(
    memory: IncidentMemory,
) -> None:
    """Symmetric counterpart: 100 repeated max-magnitude (-0.2) calls
    from a fresh prior each add a full 1.0 pseudocount to beta:
        alpha = 2 (unchanged), beta = 2 + 100*1.0 = 102
        success_score = 2*2/(2+102) = 4/104 = 1/26 = 0.03846...
    -- clearly trending toward 0.0, but strictly above it.
    """
    memory.add(make_record("demoted-001"))  # fresh: alpha=beta=2.0
    for _ in range(100):
        out = um_module.apply_reflection_to_memory({"demoted-001": -0.2})
    assert out["updated"]["demoted-001"]["new_score"] > 0.0

    hit = memory.query("anything", k=1)[0]
    assert hit["metadata"]["success_score"] == pytest.approx(1 / 26)
    assert hit["metadata"]["success_score"] > 0.0
