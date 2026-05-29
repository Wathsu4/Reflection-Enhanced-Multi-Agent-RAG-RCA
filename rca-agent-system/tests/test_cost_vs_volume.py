"""Unit tests for the cost-vs-volume simulation (E6.3). Pure arithmetic."""

from __future__ import annotations

import math

from scripts.cost_vs_volume import simulate


def test_default_headline():
    s = simulate(1000, 5.0, 4)
    assert s["incidents"] == 50
    assert s["gated_gemini_calls"] == 200
    assert s["ungated_gemini_calls"] == 4000
    assert s["saved_gemini_calls"] == 3800
    assert s["reduction_factor"] == 20.0


def test_reduction_equals_volume_to_incident_ratio():
    # reduction factor == total / incidents == 100 / incident_pct
    s = simulate(2000, 4.0, 3)
    assert s["incidents"] == 80
    assert s["reduction_factor"] == 25.0  # 100/4


def test_calls_per_rca_scales_both_sides_equally():
    s2 = simulate(1000, 5.0, 2)
    s8 = simulate(1000, 5.0, 8)
    # call count scales, but the *ratio* is invariant to calls_per_rca
    assert s2["reduction_factor"] == s8["reduction_factor"] == 20.0
    assert s8["gated_gemini_calls"] == 4 * s2["gated_gemini_calls"]


def test_zero_incident_rate_is_infinite_reduction():
    s = simulate(1000, 0.0, 4)
    assert s["incidents"] == 0
    assert s["gated_gemini_calls"] == 0
    assert math.isinf(s["reduction_factor"])


def test_wall_time_gated_is_faster():
    s = simulate(1000, 5.0, 4)
    assert s["gated_wall_s"] < s["ungated_wall_s"]
    assert s["wall_speedup"] > 1.0
