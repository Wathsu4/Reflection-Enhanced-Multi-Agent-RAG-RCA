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


# ---------- Phase 1: deterministic delta gating ----------
# (How-To-Improve/TIER0_PLAN.md SS4 / SS6)


def test_positive_delta_dropped_if_not_in_used_incident_ids() -> None:
    out = record_reflection(
        {"a": 0.15},
        "medium",
        "r",
        used_incident_ids=[],
        retrieved_incident_ids=["a"],
    )
    assert "a" not in out["incident_score_deltas"]
    assert out["_debug"]["positive_dropped_count"] == 1
    assert out["_debug"]["negative_dropped_count"] == 0


def test_positive_delta_kept_if_in_used_incident_ids() -> None:
    out = record_reflection(
        {"a": 0.15},
        "medium",
        "r",
        used_incident_ids=["a"],
        retrieved_incident_ids=["a"],
    )
    assert out["incident_score_deltas"] == {"a": 0.15}
    assert out["_debug"]["positive_dropped_count"] == 0


def test_negative_deltas_within_cap_are_all_kept() -> None:
    """N_retrieved=5 -> cap = ceil(5*0.4) = 2. Two proposed negatives both
    fit under the cap."""
    out = record_reflection(
        {"a": -0.1, "b": -0.15},
        "low",
        "r",
        used_incident_ids=[],
        retrieved_incident_ids=["a", "b", "c", "d", "e"],
    )
    assert out["incident_score_deltas"] == {"a": -0.1, "b": -0.15}
    assert out["_debug"]["negative_dropped_count"] == 0


def test_negative_deltas_exceeding_cap_keep_largest_magnitude() -> None:
    """N_retrieved=5 -> cap = 2. Three negatives proposed; the smallest-
    magnitude one ("c", -0.05) must be the one dropped, not an arbitrary
    one."""
    out = record_reflection(
        {"a": -0.2, "b": -0.1, "c": -0.05},
        "low",
        "r",
        used_incident_ids=[],
        retrieved_incident_ids=["a", "b", "c", "d", "e"],
    )
    assert out["incident_score_deltas"] == {"a": -0.2, "b": -0.1}
    assert "c" not in out["incident_score_deltas"]
    assert out["_debug"]["negative_dropped_count"] == 1


def test_negative_cap_rounds_up_for_small_retrieved_sets() -> None:
    """N_retrieved=1 -> ceil(1*0.4)=1: a single retrieved-and-irrelevant
    incident can still be penalized. This is intended -- the cap must not
    zero out all negative signal when only 1-2 incidents were retrieved."""
    out = record_reflection(
        {"only": -0.1},
        "low",
        "r",
        used_incident_ids=[],
        retrieved_incident_ids=["only"],
    )
    assert out["incident_score_deltas"] == {"only": -0.1}
    assert out["_debug"]["negative_dropped_count"] == 0


def test_zero_delta_dropped_regardless_of_used_incident_ids() -> None:
    """A 0.0 delta is a no-op and is always dropped, whether or not the
    gate is active (even in the back-compat None/None call shape)."""
    out_gated = record_reflection(
        {"a": 0.0}, "medium", "r", used_incident_ids=["a"], retrieved_incident_ids=["a"]
    )
    assert out_gated["incident_score_deltas"] == {}

    out_backcompat = record_reflection({"a": 0.0}, "medium", "r")
    assert out_backcompat["incident_score_deltas"] == {}


def test_none_ids_reproduce_pre_phase1_behavior_exactly() -> None:
    """Explicit backward-compatibility pin: omitting both new params must
    behave exactly like the pre-Phase-1 tool for non-zero deltas -- no
    id-based gating applied, only the existing clamp."""
    out = record_reflection({"a": 0.15, "b": -0.1, "c": 5.0}, "high", "r")
    assert out["incident_score_deltas"] == {"a": 0.15, "b": -0.1, "c": 0.2}
    assert out["_debug"]["positive_dropped_count"] == 0
    assert out["_debug"]["negative_dropped_count"] == 0


def test_id_not_in_retrieved_incident_ids_is_dropped() -> None:
    """A hallucinated id that was never actually retrieved can't be
    verified against either gate -- drop it, whichever sign the delta
    has, even if the reflection agent also (wrongly) claims it was used."""
    out = record_reflection(
        {"ghost-pos": 0.15, "ghost-neg": -0.1, "real": 0.1},
        "medium",
        "r",
        used_incident_ids=["ghost-pos", "ghost-neg", "real"],
        retrieved_incident_ids=["real"],
    )
    assert out["incident_score_deltas"] == {"real": 0.1}
    assert out["_debug"]["positive_dropped_count"] == 1
    assert out["_debug"]["negative_dropped_count"] == 1


def test_negative_cap_disabled_when_retrieved_incident_ids_omitted() -> None:
    """`retrieved_incident_ids=None` disables both the retrieved-universe
    filter and the negative cap, independently of `used_incident_ids`."""
    out = record_reflection(
        {"a": -0.2, "b": -0.2, "c": -0.2},
        "low",
        "r",
        used_incident_ids=[],
    )
    assert out["incident_score_deltas"] == {"a": -0.2, "b": -0.2, "c": -0.2}
    assert out["_debug"]["negative_dropped_count"] == 0


def test_positive_gate_disabled_but_retrieved_universe_filter_still_applies() -> None:
    """`used_incident_ids=None` disables the "must be used" check for
    positive deltas, but if `retrieved_incident_ids` IS known, the
    retrieved-universe filter still applies independently -- the two
    gates are controlled by their own parameter, not paired."""
    out = record_reflection(
        {"in_kb": 0.15, "ghost": 0.1},
        "medium",
        "r",
        retrieved_incident_ids=["in_kb"],
    )
    assert out["incident_score_deltas"] == {"in_kb": 0.15}
    assert "ghost" not in out["incident_score_deltas"]
    assert out["_debug"]["positive_dropped_count"] == 1


def test_malformed_id_list_arguments_are_ignored_gracefully() -> None:
    """A non-list value for either new param must degrade to "not
    provided" (gate disabled) rather than raising."""
    out = record_reflection(
        {"a": 0.1},
        "medium",
        "r",
        used_incident_ids="not-a-list",  # type: ignore[arg-type]
        retrieved_incident_ids=123,  # type: ignore[arg-type]
    )
    assert out["incident_score_deltas"] == {"a": 0.1}


def test_debug_key_present_and_does_not_leak_into_deltas() -> None:
    out = record_reflection({"a": 0.1}, "high", "r")
    assert "_debug" in out
    assert set(out["_debug"].keys()) == {"positive_dropped_count", "negative_dropped_count"}
    assert "_debug" not in out["incident_score_deltas"]
