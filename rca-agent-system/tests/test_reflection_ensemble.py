"""Tests for Tier 0 Phase 4's multi-sample reflection ensembling.

(How-To-Improve/TIER0_PLAN.md SS4/SS9)

Pure-Python aggregation tests need no Gemini key. The concurrency and
graceful-degradation tests monkeypatch `_sample_reflection` (the one
function that actually calls out to Gemini) so `run_ensemble`'s
orchestration logic (asyncio.gather usage, gating, aggregation) is
exercised without any network access.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import rca_system.tools.reflection_ensemble as re_module
from rca_system.tools.reflection_ensemble import aggregate_samples


# ---------- aggregate_samples (mean-of-proposed-deltas) ----------


def test_aggregate_samples_means_deltas_across_all_three() -> None:
    samples = [
        {"a": 0.1, "b": -0.1},
        {"a": 0.2, "b": -0.2},
        {"a": 0.15, "b": -0.15},
    ]
    out = aggregate_samples(samples)
    assert out["a"] == pytest.approx(0.15)
    assert out["b"] == pytest.approx(-0.15)


def test_aggregate_samples_handles_disagreement_on_which_ids_got_a_delta() -> None:
    """An id proposed by zero samples gets no entry; an id proposed by
    only SOME samples is averaged over just those (not divided by the
    total sample count)."""
    samples = [
        {"a": 0.2},
        {"a": 0.1, "b": -0.1},
        {},  # this sample proposed nothing at all
    ]
    out = aggregate_samples(samples)
    assert out["a"] == pytest.approx((0.2 + 0.1) / 2)
    assert out["b"] == pytest.approx(-0.1)
    assert "c" not in out


def test_aggregate_samples_empty_input_returns_empty_dict() -> None:
    assert aggregate_samples([]) == {}
    assert aggregate_samples([{}, {}, {}]) == {}


def test_aggregate_samples_outlier_does_not_dominate_the_mean() -> None:
    """One wildly-different sample among 3 must not pull the aggregate
    all the way to itself -- the other two agree closely, so the mean
    should stay much closer to their consensus."""
    samples = [
        {"a": 0.15},
        {"a": 0.18},
        {"a": -0.2},  # outlier: opposite sign, max magnitude
    ]
    out = aggregate_samples(samples)
    consensus = (0.15 + 0.18) / 2
    assert out["a"] == pytest.approx((0.15 + 0.18 - 0.2) / 3)
    # The aggregate must land closer to the two agreeing samples than to
    # the lone outlier.
    assert abs(out["a"] - consensus) < abs(out["a"] - (-0.2))


# ---------- _majority_quality ----------


def test_majority_quality_picks_clear_winner() -> None:
    assert re_module._majority_quality(["high", "high", "low"]) == "high"


def test_majority_quality_tie_breaks_toward_most_conservative() -> None:
    """low > medium > high in a tie (TIER0_PLAN.md SS4)."""
    assert re_module._majority_quality(["high", "medium"]) == "medium"
    assert re_module._majority_quality(["high", "low"]) == "low"
    assert re_module._majority_quality(["medium", "low"]) == "low"
    assert re_module._majority_quality(["high", "medium", "low"]) == "low"


def test_majority_quality_ignores_unrecognised_values() -> None:
    assert re_module._majority_quality(["high", "unknown", "high"]) == "high"


def test_majority_quality_all_unrecognised_returns_unknown() -> None:
    assert re_module._majority_quality(["unknown", "unknown"]) == "unknown"
    assert re_module._majority_quality([]) == "unknown"


# ---------- run_ensemble orchestration (mocked sampling) ----------


def _sample(delta_a: float | None, quality: str, used: list[str] | None = None) -> dict:
    deltas = {} if delta_a is None else {"a": delta_a}
    return {
        "incident_score_deltas": deltas,
        "overall_quality": quality,
        "rationale": f"sample rationale ({quality})",
        "used_incident_ids": used if used is not None else (["a"] if delta_a else []),
    }


async def test_run_ensemble_aggregates_across_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 3)

    calls = [
        (_sample(0.1, "high"), 100),
        (_sample(0.2, "high"), 120),
        (_sample(0.15, "medium"), 110),
    ]

    async def fake_sample(client, log_chunk, retrieval_output, reasoning_output):
        return calls.pop(0)

    monkeypatch.setattr(re_module, "_sample_reflection", fake_sample)

    out = await re_module.run_ensemble(
        "log", {"hits": [{"incident_id": "a"}]}, {"used_incident_ids": ["a"]}
    )
    assert out["incident_score_deltas"]["a"] == pytest.approx((0.1 + 0.2 + 0.15) / 3)
    assert out["overall_quality"] == "high"
    assert out["_debug"]["ensemble_size"] == 3
    assert out["_debug"]["ensemble_succeeded"] == 3
    assert out["_debug"]["ensemble_agreement"] == pytest.approx(round(2 / 3, 3))
    assert out["_debug"]["ensemble_total_tokens"] == 330


async def test_run_ensemble_size_one_reproduces_single_sample_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`reflection_ensemble_size == 1` must degenerate to exactly that
    one (gated) sample's own values."""
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 1)

    async def fake_sample(client, log_chunk, retrieval_output, reasoning_output):
        return _sample(0.12, "medium"), 100

    monkeypatch.setattr(re_module, "_sample_reflection", fake_sample)

    out = await re_module.run_ensemble(
        "log", {"hits": [{"incident_id": "a"}]}, {"used_incident_ids": ["a"]}
    )
    assert out["incident_score_deltas"] == {"a": pytest.approx(0.12)}
    assert out["overall_quality"] == "medium"
    assert out["_debug"]["ensemble_size"] == 1
    assert out["_debug"]["ensemble_agreement"] == pytest.approx(1.0)
    assert out["_debug"]["ensemble_total_tokens"] == 100


async def test_run_ensemble_degrades_gracefully_when_one_sample_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If one of N concurrent calls fails (per `_sample_reflection`'s own
    contract of swallowing exceptions and returning `(None, 0)` -- see
    `test_sample_reflection_swallows_exceptions_and_returns_none`), the
    aggregation must proceed over the surviving samples rather than
    crashing the whole pipeline run."""
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 3)

    calls = [(_sample(0.1, "high"), 100), (_sample(0.2, "high"), 100), (None, 0)]

    async def flaky_sample(client, log_chunk, retrieval_output, reasoning_output):
        return calls.pop(0)

    monkeypatch.setattr(re_module, "_sample_reflection", flaky_sample)

    out = await re_module.run_ensemble(
        "log", {"hits": [{"incident_id": "a"}]}, {"used_incident_ids": ["a"]}
    )
    assert out["incident_score_deltas"]["a"] == pytest.approx((0.1 + 0.2) / 2)
    assert out["_debug"]["ensemble_size"] == 3
    assert out["_debug"]["ensemble_succeeded"] == 2
    assert out["_debug"]["ensemble_total_tokens"] == 200


async def test_sample_reflection_swallows_exceptions_and_returns_none() -> None:
    """`_sample_reflection` itself -- not just the orchestrator -- must
    never raise, since it's the one function that actually talks to
    Gemini and can hit network errors, timeouts, or malformed JSON."""

    class _ExplodingClient:
        class aio:  # noqa: N801 -- mirrors genai.Client's attribute shape
            class models:
                @staticmethod
                async def generate_content(**kwargs):
                    raise RuntimeError("simulated network failure")

    result, tokens = await re_module._sample_reflection(_ExplodingClient(), "log", "{}", "{}")
    assert result is None
    assert tokens == 0


async def test_run_ensemble_all_samples_failing_returns_empty_neutral_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 3)

    async def always_fails(client, log_chunk, retrieval_output, reasoning_output):
        return None, 0

    monkeypatch.setattr(re_module, "_sample_reflection", always_fails)

    out = await re_module.run_ensemble("log", {"hits": []}, {})
    assert out["incident_score_deltas"] == {}
    assert out["overall_quality"] == "unknown"
    assert out["_debug"]["ensemble_succeeded"] == 0
    assert out["_debug"]["ensemble_total_tokens"] == 0


async def test_run_ensemble_issues_samples_concurrently_not_sequentially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms `asyncio.gather` (or equivalent) is actually used -- N=3
    artificially-delayed samples must complete in roughly ONE delay
    period's worth of wall-clock time, not three."""
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 3)
    delay = 0.2

    async def slow_sample(client, log_chunk, retrieval_output, reasoning_output):
        await asyncio.sleep(delay)
        return _sample(0.1, "high"), 100

    monkeypatch.setattr(re_module, "_sample_reflection", slow_sample)

    started = time.perf_counter()
    await re_module.run_ensemble("log", {"hits": []}, {})
    elapsed = time.perf_counter() - started

    # Sequential execution would take >= 3*delay (0.6s); concurrent
    # execution should take roughly 1*delay. Generous margin for CI
    # scheduling jitter.
    assert elapsed < delay * 2, (
        f"Expected concurrent execution (~{delay}s), took {elapsed:.3f}s -- "
        "samples may be running sequentially instead of via asyncio.gather"
    )


async def test_run_ensemble_reports_degraded_status_when_every_sample_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"No incident earned a delta" and "we never got a judgment" both
    produce an empty delta map, so the status field is the only way
    downstream can tell them apart."""
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 2)

    async def always_fails(client, log_chunk, retrieval_output, reasoning_output):
        return None, 0

    monkeypatch.setattr(re_module, "_sample_reflection", always_fails)

    out = await re_module.run_ensemble("log", {"hits": []}, {})
    assert out["status"] == "degraded"
    assert out["_debug"]["ensemble_failed"] == 2


async def test_run_ensemble_stays_recorded_when_a_sample_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 2)
    calls = [(_sample(0.1, "high"), 100), (None, 0)]

    async def flaky_sample(client, log_chunk, retrieval_output, reasoning_output):
        return calls.pop(0)

    monkeypatch.setattr(re_module, "_sample_reflection", flaky_sample)

    out = await re_module.run_ensemble(
        "log", {"hits": [{"incident_id": "a"}]}, {"used_incident_ids": ["a"]}
    )
    assert out["status"] == "recorded"
    assert out["_debug"]["ensemble_failed"] == 1


async def test_sample_reflection_logs_the_swallowed_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _ExplodingClient:
        class aio:  # noqa: N801 -- mirrors genai.Client's attribute shape
            class models:
                @staticmethod
                async def generate_content(**kwargs):
                    raise RuntimeError("simulated network failure")

    with caplog.at_level("WARNING"):
        await re_module._sample_reflection(_ExplodingClient(), "log", "{}", "{}")  # type: ignore[arg-type]
    assert "Reflection sample failed" in caplog.text
    assert "simulated network failure" in caplog.text


def test_extract_retrieved_ids_logs_unparseable_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unparseable retrieval_output disables both delta gates, so it
    must not be a silent degradation."""
    with caplog.at_level("WARNING"):
        assert re_module._extract_retrieved_ids("{not json") == []
    assert "Could not extract retrieved incident ids" in caplog.text


async def test_run_ensemble_reports_client_construction_failure_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A missing/invalid API key must not raise out of the tool: that
    aborts a run whose reasoning stage already produced a hypothesis."""
    monkeypatch.setattr(re_module.settings, "reflection_ensemble_size", 2)

    def exploding_client(**kwargs):
        raise ValueError("No API key was provided.")

    monkeypatch.setattr(re_module.genai, "Client", exploding_client)

    with caplog.at_level("ERROR"):
        out = await re_module.run_ensemble("log", {"hits": []}, {})

    assert out["status"] == "degraded"
    assert "No API key was provided." in out["error"]
    assert out["incident_score_deltas"] == {}
    assert "could not create a Gemini client" in caplog.text
