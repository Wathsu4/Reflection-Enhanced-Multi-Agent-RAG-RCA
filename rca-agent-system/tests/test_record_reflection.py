"""Unit tests for the `record_reflection` tool.

This tool is a clamp + structure step. It must never raise on the kinds
of malformed input Gemini occasionally produces, because if it does the
whole pipeline halts.
"""

from __future__ import annotations

from rca_system.tools.record_reflection import record_reflection


# ---------- happy path ----------


def test_returns_status_recorded() -> None:
    out = record_reflection({"a": 0.1}, "high", "looks good")
    assert out["status"] == "recorded"


def test_passes_through_well_formed_inputs() -> None:
    out = record_reflection(
        {"a": 0.15, "b": -0.1},
        "medium",
        "Some retrieved incidents helped, others were noise.",
    )
    assert out["incident_score_deltas"] == {"a": 0.15, "b": -0.1}
    assert out["overall_quality"] == "medium"
    assert out["rationale"].startswith("Some retrieved")


# ---------- delta clamping ----------


def test_clamps_deltas_to_plus_minus_zero_point_two() -> None:
    """Per the docstring contract: any delta outside [-0.2, +0.2] must
    be clamped, not rejected. This is the safety net against a
    hallucinating reflection agent wrecking memory in one bad run."""
    out = record_reflection(
        {"too_high": 5.0, "too_low": -3.0, "ok": 0.05},
        "high",
        "test",
    )
    assert out["incident_score_deltas"] == {
        "too_high": 0.2,
        "too_low": -0.2,
        "ok": 0.05,
    }


def test_skips_non_numeric_delta_values() -> None:
    """A bad value for one incident must not poison the whole batch."""
    out = record_reflection(
        {"good": 0.1, "bad": "not a number"},
        "medium",
        "r",
    )
    assert "good" in out["incident_score_deltas"]
    assert out["incident_score_deltas"]["good"] == 0.1
    assert "bad" not in out["incident_score_deltas"]


# ---------- robustness to weird shapes ----------


def test_accepts_list_of_objects_format() -> None:
    """Gemini sometimes hands us `[{incident_id, delta}]` instead of
    a flat dict. We reshape rather than fail."""
    out = record_reflection(
        [
            {"incident_id": "x", "delta": 0.1},
            {"incident_id": "y", "delta": -0.1},
        ],  # type: ignore[arg-type]
        "high",
        "r",
    )
    assert out["incident_score_deltas"] == {"x": 0.1, "y": -0.1}


def test_handles_completely_garbage_deltas_argument() -> None:
    out = record_reflection("nope", "high", "r")  # type: ignore[arg-type]
    assert out["incident_score_deltas"] == {}
    assert out["status"] == "recorded"


# ---------- overall_quality validation ----------


def test_normalises_overall_quality_case() -> None:
    assert record_reflection({}, "HIGH", "r")["overall_quality"] == "high"
    assert record_reflection({}, " Medium ", "r")["overall_quality"] == "medium"


def test_unknown_overall_quality_is_tagged_unknown() -> None:
    """Don't silently coerce -- tag misformatted verdicts so they're
    visible in logs and tests."""
    out = record_reflection({}, "excellent", "r")
    assert out["overall_quality"] == "unknown"


# ---------- rationale handling ----------


def test_rationale_is_stripped_string() -> None:
    out = record_reflection({}, "high", "  some text  ")
    assert out["rationale"] == "some text"


def test_none_rationale_becomes_empty_string() -> None:
    out = record_reflection({}, "high", None)  # type: ignore[arg-type]
    assert out["rationale"] == ""
