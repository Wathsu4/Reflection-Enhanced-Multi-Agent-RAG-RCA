"""Tests for the ReAct (Reason + Act) single-agent baseline."""

from __future__ import annotations

from rca_system.ablations import (
    _REACT_MAX_TOOL_CALLS,
    _react_tool_call_cap,
    build_react_agent,
    build_root_agent,
)


class _FakeToolContext:
    """Minimal stand-in for ADK's ToolContext: a dict-like `.state`."""

    def __init__(self) -> None:
        self.state: dict[str, object] = {}


def test_react_builds_as_single_agent_with_retrieval_tool():
    agent = build_root_agent("react")
    # Single agent, not a SequentialAgent pipeline.
    assert not getattr(agent, "sub_agents", [])
    assert agent.output_key == "final_output"
    assert agent.before_tool_callback is not None
    tool_names = [getattr(t, "name", "") for t in (agent.tools or [])]
    assert any("retrieve" in n for n in tool_names), tool_names


def test_build_react_agent_helper_matches_factory():
    a = build_react_agent()
    assert a.name == "rca_react_agent"
    assert a.before_tool_callback is not None


def test_react_tool_call_cap_allows_then_blocks():
    ctx = _FakeToolContext()
    # The first N calls are allowed (callback returns None -> real tool runs).
    for _ in range(_REACT_MAX_TOOL_CALLS):
        assert _react_tool_call_cap(None, {}, ctx) is None
    assert ctx.state["_react_tool_calls"] == _REACT_MAX_TOOL_CALLS

    # The next call is short-circuited with an empty, "answer now" result.
    blocked = _react_tool_call_cap(None, {}, ctx)
    assert isinstance(blocked, dict)
    assert blocked["hits"] == []
    assert "budget" in blocked["note"].lower()


def test_react_is_a_registered_ablation():
    from rca_system.ablations import ABLATIONS

    assert "react" in ABLATIONS
