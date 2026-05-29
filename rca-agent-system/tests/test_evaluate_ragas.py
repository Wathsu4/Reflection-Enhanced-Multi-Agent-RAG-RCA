"""Unit tests for the RAGAS-triad metrics (E4.1).

The metric functions take injected `ask` / `embed` callables, so we test
them without any Gemini call or model download.
"""

from __future__ import annotations

import pytest

from scripts.evaluate_ragas import (
    _cosine,
    _parse_json,
    answer_relevancy,
    context_precision,
    faithfulness,
)


# -------------------- helpers --------------------


def test_parse_json_strips_code_fences():
    assert _parse_json('```json\n[1, 2, 3]\n```') == [1, 2, 3]
    assert _parse_json("[true, false]") == [True, False]
    assert _parse_json("not json") is None


def test_cosine():
    assert _cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert _cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert _cosine([0, 0], [1, 1]) == 0.0  # zero vector guard


# -------------------- context precision (deterministic) --------------------


def test_context_precision_none_when_nothing_retrieved():
    assert context_precision([], ["a"]) is None


def test_context_precision_zero_when_none_used():
    assert context_precision(["a", "b", "c"], []) == 0.0
    assert context_precision(["a", "b"], ["x", "y"]) == 0.0


def test_context_precision_perfect_when_relevant_ranked_first():
    # both relevant items are at the top -> AP = 1.0
    assert context_precision(["a", "b", "c"], ["a", "b"]) == 1.0


def test_context_precision_rank_aware():
    # relevant item is 2nd of 3; AP = (1/2) / 1 = 0.5
    assert context_precision(["x", "a", "y"], ["a"]) == 0.5
    # relevant at positions 1 and 3: (1/1 + 2/3)/2 = 0.8333
    assert context_precision(["a", "x", "b"], ["a", "b"]) == pytest.approx(0.8333, abs=1e-3)


# -------------------- faithfulness (mocked Gemini) --------------------


def _make_ask(claims, verdicts):
    async def ask(prompt: str) -> str:
        if "Extract the distinct factual claims" in prompt:
            return claims
        return verdicts

    return ask


async def test_faithfulness_fraction_supported():
    ask = _make_ask('["c1", "c2", "c3"]', "[true, false, true]")
    score, supported, total = await faithfulness("report", ["ctx"], ask=ask)
    assert (supported, total) == (2, 3)
    assert score == pytest.approx(0.6667, abs=1e-3)


async def test_faithfulness_none_without_context():
    ask = _make_ask("[]", "[]")
    score, supported, total = await faithfulness("report", [], ask=ask)
    assert score is None and total == 0


async def test_faithfulness_handles_unparseable_claims():
    ask = _make_ask("garbage not json", "[]")
    score, _, _ = await faithfulness("report", ["ctx"], ask=ask)
    assert score is None


# -------------------- answer relevancy (mocked Gemini + fake embed) --------------------


async def test_answer_relevancy_mean_cosine():
    async def ask(prompt: str) -> str:
        return '["q1", "q2"]'

    # chunk identical to q1 (cos 1), orthogonal to q2 (cos 0) -> mean 0.5
    vectors = {
        "chunk": [1.0, 0.0],
        "q1": [1.0, 0.0],
        "q2": [0.0, 1.0],
    }

    def embed(texts):
        # texts = [chunk, q1, q2]
        return [vectors["chunk"], vectors["q1"], vectors["q2"]]

    rel = await answer_relevancy("report", "chunk", ask=ask, embed=embed)
    assert rel == pytest.approx(0.5, abs=1e-6)


async def test_answer_relevancy_none_without_report():
    async def ask(prompt: str) -> str:
        return "[]"

    rel = await answer_relevancy("", "chunk", ask=ask, embed=lambda t: [])
    assert rel is None
