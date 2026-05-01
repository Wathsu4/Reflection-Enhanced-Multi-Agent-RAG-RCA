"""Smoke tests for the synthetic log generator. These run without the
trained model and don't require any heavy ML dependencies beyond stdlib.
"""

from __future__ import annotations

from app.log_generator import generate_log_chunk


def test_normal_profile_emits_no_error_keywords():
    chunk, severity = generate_log_chunk(profile="normal", num_lines=30, seed=1)
    assert severity == "NORMAL"
    assert chunk.count("\n") == 29
    upper = chunk.upper()
    # Loosely verify we didn't accidentally pull from another pool.
    for forbidden in ("FATAL", "ERROR", " WARN "):
        assert forbidden not in upper, f"NORMAL profile leaked {forbidden!r}: {chunk[:200]}"


def test_fatal_profile_dominant_severity():
    chunk, severity = generate_log_chunk(profile="fatal", num_lines=30, seed=2)
    assert severity == "FATAL_OR_CRITICAL"
    upper = chunk.upper()
    assert "FATAL" in upper or "OOMKILLED" in upper


def test_mixed_profile_returns_known_severity():
    chunk, severity = generate_log_chunk(profile="mixed", num_lines=30, seed=42)
    assert severity in {"NORMAL", "WARNING", "ERROR", "FATAL_OR_CRITICAL"}
    assert chunk.count("\n") == 29


def test_seed_reproducibility():
    a, _ = generate_log_chunk(profile="error", num_lines=10, seed=99)
    b, _ = generate_log_chunk(profile="error", num_lines=10, seed=99)
    assert a == b


def test_invalid_profile_raises():
    import pytest

    with pytest.raises(ValueError):
        generate_log_chunk(profile="bogus", num_lines=10)
