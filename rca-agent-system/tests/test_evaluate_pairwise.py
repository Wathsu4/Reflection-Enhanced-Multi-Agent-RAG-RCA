"""Unit tests for the bias-mitigated pairwise judge (E4.2).

The judge `ask` callable is injected, so we test verdict normalisation,
vote aggregation, and the order-consistency (position-bias) diagnostic
without any Gemini call.
"""

from __future__ import annotations

from scripts.evaluate_pairwise import (
    aggregate_votes,
    judge_scenario,
    normalize_verdict,
)


# -------------------- normalize_verdict --------------------


def test_normalize_not_swapped():
    assert normalize_verdict("A", swapped=False) == "a"
    assert normalize_verdict("B", swapped=False) == "b"
    assert normalize_verdict("tie", swapped=False) == "tie"
    assert normalize_verdict("garbage", swapped=False) == "tie"


def test_normalize_swapped_inverts_ab():
    # When B/A order, a raw "A" means variant_b won.
    assert normalize_verdict("A", swapped=True) == "b"
    assert normalize_verdict("B", swapped=True) == "a"
    assert normalize_verdict("tie", swapped=True) == "tie"


# -------------------- aggregate_votes --------------------


def test_aggregate_majority():
    assert aggregate_votes(["a", "a", "b"]) == "a"
    assert aggregate_votes(["b", "b", "a"]) == "b"
    assert aggregate_votes(["a", "b", "tie"]) == "tie"  # a==b -> tie
    assert aggregate_votes(["tie", "tie", "a"]) == "a"


# -------------------- judge_scenario (mocked ask) --------------------


async def test_judge_detects_pure_position_bias():
    """A judge that always answers 'A' (positional) yields an overall tie
    and is flagged order-inconsistent."""

    async def ask(prompt: str, temperature: float) -> str:
        return "A"

    r = await judge_scenario("s1", "log", "gt", "report_a", "report_b", ask=ask, n_each=3)
    # 3 A/B -> 'a', 3 B/A (swapped) -> 'b'  => tie, inconsistent
    assert r.votes == ["a", "a", "a", "b", "b", "b"]
    assert r.winner == "tie"
    assert r.order_consistent is False
    assert r.error is None


async def test_judge_content_based_is_consistent():
    """A judge that picks whichever report contains the winning marker,
    regardless of position, is order-consistent and picks variant A."""

    async def ask(prompt: str, temperature: float) -> str:
        a_idx = prompt.index("REPORT A:")
        b_idx = prompt.index("REPORT B:")
        block_a = prompt[a_idx:b_idx]
        block_b = prompt[b_idx:]
        if "WINNER" in block_a:
            return "A"
        if "WINNER" in block_b:
            return "B"
        return "tie"

    r = await judge_scenario(
        "s1", "log", "gt", "WINNER report", "loser report", ask=ask, n_each=3
    )
    assert r.winner == "a"
    assert r.votes == ["a", "a", "a", "a", "a", "a"]
    assert r.order_consistent is True


async def test_judge_propagates_error():
    async def ask(prompt: str, temperature: float) -> str:
        raise RuntimeError("503 UNAVAILABLE")

    r = await judge_scenario("s1", "log", "gt", "a", "b", ask=ask, n_each=3)
    assert r.error is not None and "503" in r.error
    assert r.winner == "tie"  # default
