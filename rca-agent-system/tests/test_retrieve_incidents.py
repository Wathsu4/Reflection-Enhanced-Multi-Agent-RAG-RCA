"""Tests for the `retrieve_incidents` ADK function tool.

The tool is a thin wrapper around `IncidentMemory.query`, plus a
re-ranking step. We monkeypatch the module-level `_memory` so the test
runs against a tmp ChromaDB rather than the prod one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import rca_system.tools.retrieve_incidents as ri_module
from rca_system.memory.chroma_store import IncidentMemory, IncidentRecord
from tests._fake_embed import FakeEmbeddingFunction


@pytest.fixture
def memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> IncidentMemory:
    mem = IncidentMemory(
        persist_dir=tmp_path / "chroma",
        collection_name="incident_memory_test",
        embedding_function=FakeEmbeddingFunction(),
    )
    # Replace the module-level singleton so the tool talks to our tmp memory.
    monkeypatch.setattr(ri_module, "_memory", mem)
    return mem


def make_record(incident_id: str, **overrides) -> IncidentRecord:
    fields = {
        "incident_id": incident_id,
        "title": "T",
        "severity": "ERROR",
        "root_cause": "RC",
        "resolution": "R",
        "tags": "t",
    }
    fields.update(overrides)
    return IncidentRecord(**fields)


def test_returns_dict_with_hits_key(memory: IncidentMemory) -> None:
    """ADK function tools must return JSON-serialisable dicts. The
    `hits` key is part of the docstring contract Gemini reads."""
    memory.add(make_record("a"))
    out = ri_module.retrieve_incidents("anything", k=1)
    assert isinstance(out, dict)
    assert "hits" in out
    assert isinstance(out["hits"], list)


def test_clamps_k_to_valid_range(memory: IncidentMemory) -> None:
    """Gemini sometimes passes nonsense k values. The tool must be
    robust without raising back into the model."""
    for i in range(3):
        memory.add(make_record(f"r-{i}"))

    # k=0 must clamp up to 1.
    assert len(ri_module.retrieve_incidents("q", k=0)["hits"]) == 1
    # k=99 must clamp down to <= number of records.
    assert len(ri_module.retrieve_incidents("q", k=99)["hits"]) == 3


def test_each_hit_has_the_documented_shape(memory: IncidentMemory) -> None:
    """Every key listed in the docstring must actually appear -- this
    is what Gemini sees as the tool's return-shape promise."""
    memory.add(
        make_record(
            "shape-001",
            title="Redis refused",
            severity="ERROR",
            root_cause="Firewall",
            resolution="Restored rule",
        )
    )
    out = ri_module.retrieve_incidents("q", k=1)
    hit = out["hits"][0]
    expected_keys = {
        "incident_id",
        "title",
        "severity",
        "root_cause",
        "resolution",
        "similarity",
        "success_score",
    }
    assert expected_keys <= hit.keys()
    assert hit["incident_id"] == "shape-001"
    assert hit["title"] == "Redis refused"


def test_dynamic_reranking_boosts_high_score_hits(
    memory: IncidentMemory,
) -> None:
    """If two records have similar similarity, the one with the higher
    success_score must surface first. This is the central "dynamic
    memory" behaviour that reflection (Phase 7) leans on."""
    # Both records have identical text -> identical similarity under
    # the fake hash embedding. The only difference is success_score.
    text = "identical body"
    memory.add(make_record("low", success_score=0.5), document_text=text)
    memory.add(make_record("high", success_score=1.5), document_text=text)

    out = ri_module.retrieve_incidents(text, k=2)
    ids_in_order = [h["incident_id"] for h in out["hits"]]
    assert ids_in_order[0] == "high", (
        f"Expected high-score record first, got {ids_in_order}"
    )


def test_calls_mark_retrieved_on_returned_hits(
    memory: IncidentMemory,
) -> None:
    """The tool must bump usage_count for every hit it returns. This
    is what powers the retrieval-popularity analytics."""
    memory.add(make_record("popular-001"))
    ri_module.retrieve_incidents("q", k=1)
    ri_module.retrieve_incidents("q", k=1)

    hit = memory.query("q", k=1)[0]
    assert hit["metadata"]["usage_count"] == 2


# ---------- Phase 3: exploration bonus / anti-starvation ----------
# (How-To-Improve/TIER0_PLAN.md SS4/SS8)


def test_exploration_bonus_never_exceeds_the_configured_weight() -> None:
    """At usage_count=0 the bonus equals exploration_bonus_weight
    exactly; for any usage_count >= 0 it must never exceed that weight
    (the formula can't blow up for any valid input), and it must
    monotonically decay as usage accumulates."""
    from rca_system.settings import settings

    max_bonus = settings.exploration_bonus_weight
    assert ri_module._exploration_bonus(0) == pytest.approx(max_bonus)

    bonuses = [ri_module._exploration_bonus(n) for n in range(0, 50)]
    assert all(0 < b <= max_bonus for b in bonuses)
    assert bonuses == sorted(bonuses, reverse=True)  # strictly decaying


def test_zeroed_incident_outranks_low_score_high_usage_competitor(
    memory: IncidentMemory,
) -> None:
    """A zeroed-out (success_score=0.0), never-retrieved incident must
    be able to outrank a competitor with a low-but-nonzero score that
    has been retrieved many times -- proves the starvation floor works.

    Regardless of their (comparable, here identical) raw similarity S:
      starved:  S*0.0    + bonus(usage=0)   = 0    + 0.1     = 0.1
      entrenched: S*0.05 + bonus(usage=100) <= 1*0.05 + 0.1*sqrt(1/101)
                                             = 0.05 + 0.00995 = 0.05995
    0.1 > 0.05995 for ANY similarity S in the valid [0, 1] range, so
    this doesn't depend on the fake embedding's exact hash output.
    """
    text = "identical body"
    memory.add(
        make_record("entrenched", success_score=0.05, usage_count=100),
        document_text=text,
    )
    memory.add(
        make_record("starved", success_score=0.0, usage_count=0),
        document_text=text,
    )

    out = ri_module.retrieve_incidents(text, k=2)
    ids_in_order = [h["incident_id"] for h in out["hits"]]
    assert ids_in_order[0] == "starved", (
        f"Expected the starved incident to outrank the entrenched "
        f"low-score competitor, got {ids_in_order}"
    )


def test_exploration_bonus_does_not_overwhelm_a_strong_match(
    memory: IncidentMemory,
) -> None:
    """A zeroed-out incident's exploration bonus (capped at
    exploration_bonus_weight, 0.1 by default) must never let it outrank
    a genuinely strong match: high similarity (here, an exact text
    match, similarity ~= 1.0) with a neutral-or-better success_score.

      strong:  ~1.0*1.0 + bonus(usage=0) = ~1.0 + 0.1 = ~1.1
      starved:  S_weak*0.0 + bonus(usage=0) = 0 + 0.1 = 0.1
    ~1.1 >> 0.1 regardless of the exact similarity value or S_weak.
    """
    memory.add(make_record("strong", success_score=1.0), document_text="exact match text")
    memory.add(make_record("starved", success_score=0.0), document_text="unrelated filler")

    out = ri_module.retrieve_incidents("exact match text", k=2)
    ids_in_order = [h["incident_id"] for h in out["hits"]]
    assert ids_in_order[0] == "strong", (
        f"A strong, neutral-scored match must not be outranked by a "
        f"zeroed-out incident's exploration bonus alone, got {ids_in_order}"
    )


def test_starved_incident_outranks_competitor_as_its_own_usage_climbs(
    memory: IncidentMemory,
) -> None:
    """Pure-Python checkpoint (TIER0_PLAN.md SS8, no live Gemini): a
    zeroed-out incident that is NEVER retrieved keeps the full
    exploration bonus forever (usage_count stays 0). A competitor that
    keeps getting picked (simulated here via direct
    `IncidentMemory.mark_retrieved` calls, standing in for repeated
    real-world retrievals by *other* queries) sees its OWN bonus decay
    as its usage_count climbs. Demonstrates the actual anti-starvation
    mechanism: a rarely-used incident's rank relative to a
    frequently-used one improves purely because the frequent one's own
    bonus keeps shrinking -- not because the zeroed incident's own
    success_score or usage ever change.

    (The formula's bonus decays with *that same incident's own* usage
    count -- "decays toward 0 as an incident accumulates retrievals",
    TIER0_PLAN.md SS4 -- so retrieving the zeroed incident itself would
    lower its own bonus, not raise it. This test demonstrates the
    mechanism precisely, rather than the literal "usage_count climbs"
    framing, which would otherwise contradict the formula.)
    """
    text = "shared body"
    memory.add(make_record("starved", success_score=0.0), document_text=text)
    # Measure this fake embedding's self-similarity once rather than
    # hard-coding a number that depends on FakeEmbeddingFunction's exact
    # hash-to-float mapping.
    similarity = memory.query(text, k=1)[0]["similarity"]
    assert similarity > 0

    # A product term just inside the exploration bonus's range (0, 0.1]
    # at usage_count=0 -- small enough that a handful of the
    # competitor's own retrievals decay its bonus below "starved"'s
    # untouched 0.1.
    target_product = 0.045
    competitor_score = target_product / similarity
    memory.add(
        make_record("competitor", success_score=competitor_score),
        document_text=text,
    )

    # Before any extra use: competitor starts ahead (real signal + max
    # bonus beats bonus-only).
    assert target_product + ri_module._exploration_bonus(0) > 0.1

    # Simulate the competitor being retrieved 5 more times by other
    # queries -- direct IncidentMemory calls, no live Gemini needed.
    for _ in range(5):
        memory.mark_retrieved(["competitor"])

    # After 5 extra retrievals (usage_count=5): bonus decays to
    # 0.1*sqrt(1/6) = 0.0408, for a total of 0.045+0.0408 = 0.0858 --
    # now under "starved"'s untouched 0.1.
    assert target_product + ri_module._exploration_bonus(5) < 0.1

    out = ri_module.retrieve_incidents(text, k=2)
    ids_in_order = [h["incident_id"] for h in out["hits"]]
    assert ids_in_order[0] == "starved", (
        f"Expected the never-retrieved zero-score incident to have "
        f"overtaken the repeatedly-retrieved low-score competitor once "
        f"the competitor's own exploration bonus decayed; got {ids_in_order}"
    )
