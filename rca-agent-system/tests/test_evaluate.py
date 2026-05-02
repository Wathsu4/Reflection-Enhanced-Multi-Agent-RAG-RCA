"""Tests for the deterministic helpers in `scripts/evaluate.py`.

We don't run the live pipeline here -- that requires Gemini quota and
would slow CI to a crawl. The pipeline-runner is integration-tested
implicitly when `evaluate.py` is run for the thesis; the helpers below
are the parts that drive the numerical conclusions, so they get
unit-test coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import evaluate as ev

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET = PROJECT_ROOT / "eval" / "incidents.jsonl"


# ---------- extract_root_cause ----------


def test_extract_root_cause_pulls_first_paragraph_under_heading() -> None:
    md = (
        "## Root cause\n"
        "Firewall rule blocked Redis port 6379.\n"
        "\n"
        "## Suggested actions\nCheck firewall.\n"
    )
    assert ev.extract_root_cause(md) == "Firewall rule blocked Redis port 6379."


def test_extract_root_cause_handles_missing_section() -> None:
    assert ev.extract_root_cause("## Other\nfoo") == ""


def test_extract_root_cause_handles_empty_input() -> None:
    assert ev.extract_root_cause("") == ""


def test_extract_root_cause_does_not_bleed_into_next_section() -> None:
    md = "## Root cause\nNetwork outage.\n## Suggested actions\nPage on-call."
    out = ev.extract_root_cause(md)
    assert out == "Network outage."
    assert "on-call" not in out


# ---------- keyword scoring ----------


def test_keyword_score_full_match() -> None:
    assert (
        ev.keyword_score(
            "Redis connection refused on port 6379",
            ["redis", "connection refused", "6379"],
        )
        == 1.0
    )


def test_keyword_score_partial_match() -> None:
    score = ev.keyword_score(
        "Redis is unreachable",
        ["redis", "connection refused", "6379"],
    )
    assert score == pytest.approx(1 / 3)


def test_keyword_score_is_case_insensitive() -> None:
    assert (
        ev.keyword_score("REDIS connection REFUSED", ["redis", "connection"])
        == 1.0
    )


def test_keyword_score_empty_keyword_list() -> None:
    assert ev.keyword_score("anything", []) == 0.0


def test_keyword_verdict_buckets() -> None:
    assert ev.keyword_verdict(0.9) == "exact"
    assert ev.keyword_verdict(0.66) == "exact"
    assert ev.keyword_verdict(0.5) == "partial"
    assert ev.keyword_verdict(0.33) == "partial"
    assert ev.keyword_verdict(0.2) == "miss"
    assert ev.keyword_verdict(0.0) == "miss"


# ---------- dataset loader ----------


def test_load_scenarios_parses_shipped_dataset() -> None:
    scenarios = ev.load_scenarios(DATASET)
    assert len(scenarios) >= 15, (
        f"Phase 10 spec calls for >= 15 scenarios; found {len(scenarios)}."
    )
    # Spot check: every scenario has the required fields populated.
    for s in scenarios:
        assert s.id
        assert s.log_chunk
        assert s.ground_truth_root_cause
        # Some OOD scenarios may have an empty list, but the type must
        # stay a list.
        assert isinstance(s.ground_truth_keywords, list)


def test_load_scenarios_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    p = tmp_path / "tiny.jsonl"
    p.write_text(
        "# header comment\n"
        "\n"
        '{"id":"x","log_chunk":"foo","ground_truth_root_cause":"bar",'
        '"ground_truth_keywords":["k"],"expected_incident_id":null}\n',
        encoding="utf-8",
    )
    out = ev.load_scenarios(p)
    assert len(out) == 1
    assert out[0].id == "x"


def test_dataset_includes_in_domain_and_ood_cases() -> None:
    """The eval set must cover both: in-domain (we expect a specific
    incident retrieval hit) and out-of-distribution (we expect the
    system to honestly say it has no close match). Otherwise we can't
    measure either capability."""
    scenarios = ev.load_scenarios(DATASET)
    in_dom = [s for s in scenarios if s.expected_incident_id is not None]
    ood = [s for s in scenarios if s.expected_incident_id is None]
    assert len(in_dom) >= 6, (
        "Need at least one in-domain scenario per seed incident; "
        f"got {len(in_dom)}."
    )
    assert len(ood) >= 1, "Need at least one OOD scenario for honest-no-match recall."


# ---------- summarize ----------


def _result(**overrides) -> ev.ScenarioResult:
    base = {
        "id": "s",
        "expected_incident_id": "i-1",
        "final_markdown": "## Root cause\nTest",
        "extracted_root_cause": "Test",
        "keyword_score": 0.5,
        "keyword_verdict": "partial",
        "expected_incident_retrieved": True,
        "top_retrieval_similarity": 0.9,
        "latency_s": 1.0,
    }
    base.update(overrides)
    return ev.ScenarioResult(**base)


def test_summarize_aggregates_verdict_counts_and_latencies() -> None:
    results = [
        _result(id="a", keyword_verdict="exact", latency_s=1.0),
        _result(id="b", keyword_verdict="exact", latency_s=2.0),
        _result(id="c", keyword_verdict="miss", latency_s=4.0),
    ]
    s = ev.summarize(results)
    assert s["n"] == 3
    assert s["keyword_verdict_counts"] == {"exact": 2, "partial": 0, "miss": 1}
    # exact + partial out of total
    assert s["keyword_accuracy_exact_or_partial"] == round(2 / 3, 3)
    # Latencies are rounded to 3dp by `summarize` for clean reporting.
    assert s["mean_latency_s"] == round(7 / 3, 3)


def test_summarize_handles_ood_scenarios_in_recall() -> None:
    """Recall should be computed only over scenarios that DECLARED an
    expected incident id. OOD entries must not push the denominator."""
    results = [
        _result(id="in", expected_incident_id="i-1", expected_incident_retrieved=True),
        _result(id="ood", expected_incident_id=None, expected_incident_retrieved=None),
    ]
    s = ev.summarize(results)
    assert s["expected_incident_retrieval_recall"] == 1.0
    assert s["n_in_domain"] == 1
    assert s["n_ood"] == 1


def test_summarize_handles_empty_input() -> None:
    assert ev.summarize([]) == {"n": 0}


# ---------- markdown report ----------


def test_render_markdown_report_contains_required_sections() -> None:
    results = [_result(id="a")]
    summary = ev.summarize(results)
    md = ev.render_markdown_report(results, summary)
    assert "# RCA pipeline evaluation" in md
    assert "## Per-scenario" in md
    assert "| a |" in md
