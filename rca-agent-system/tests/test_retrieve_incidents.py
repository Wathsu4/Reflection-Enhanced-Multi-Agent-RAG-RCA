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
