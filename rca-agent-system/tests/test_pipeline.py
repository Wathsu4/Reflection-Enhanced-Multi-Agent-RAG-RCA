"""Tests for the Phase 7 pipeline composition.

We don't run the full Gemini round-trip here -- that's expensive and
non-deterministic. Instead we verify the static structure:
  * `root_agent` is a SequentialAgent
  * Has the four expected sub-agents in the right order
  * Each sub-agent declares the right `output_key`
  * Inter-agent state references (e.g. `{retrieval_output}` in the
    reasoning instruction) name keys that are actually written by an
    upstream agent
  * Each sub-agent that needs a tool actually has the tool attached

If any of these break, the pipeline silently produces empty / wrong
state -- catching it here is much cheaper than catching it via a 30s
live ADK run.
"""

from __future__ import annotations

import re

import pytest
from google.adk.agents import Agent, SequentialAgent

from rca_system.agent import root_agent
from rca_system.agents import (
    memory_update_agent,
    reasoning_agent,
    reflection_agent,
    retrieval_agent,
)


# ---------- root composition ----------


def test_root_agent_is_a_sequential_agent() -> None:
    assert isinstance(root_agent, SequentialAgent)


def test_root_agent_has_four_subagents_in_pipeline_order() -> None:
    """The order is part of the contract: each stage reads state
    written by all earlier stages. Reordering is a breaking change."""
    expected_names = [
        "retrieval_agent",
        "reasoning_agent",
        "reflection_agent",
        "memory_update_agent",
    ]
    actual_names = [c.name for c in root_agent.sub_agents]
    assert actual_names == expected_names


def test_each_subagent_is_the_canonical_singleton() -> None:
    """If any of these aren't the same instance imported from
    `rca_system.agents`, two different agents with identical names will
    be live in the process and ADK will route inconsistently."""
    by_name = {c.name: c for c in root_agent.sub_agents}
    assert by_name["retrieval_agent"] is retrieval_agent
    assert by_name["reasoning_agent"] is reasoning_agent
    assert by_name["reflection_agent"] is reflection_agent
    assert by_name["memory_update_agent"] is memory_update_agent


# ---------- per-stage output_key contracts ----------

EXPECTED_OUTPUT_KEYS = {
    "retrieval_agent": "retrieval_output",
    "reasoning_agent": "reasoning_output",
    "reflection_agent": "reflection_output",
    "memory_update_agent": "final_output",
}


@pytest.mark.parametrize(
    "agent_name,expected_key", list(EXPECTED_OUTPUT_KEYS.items())
)
def test_subagent_output_key(agent_name: str, expected_key: str) -> None:
    by_name = {c.name: c for c in root_agent.sub_agents}
    agent = by_name[agent_name]
    assert isinstance(agent, Agent)
    assert agent.output_key == expected_key, (
        f"{agent_name}.output_key must be {expected_key!r} "
        f"(downstream agents read state[{expected_key!r}])"
    )


# ---------- inter-agent state references resolve ----------


def _state_keys_in_instruction(instruction: str) -> set[str]:
    """Pull `{key}` and `{key?}` placeholders out of an instruction."""
    return {m.rstrip("?") for m in re.findall(r"\{([a-zA-Z_][a-zA-Z_0-9]*\??)\}", instruction)}


def test_reasoning_references_only_upstream_state_keys() -> None:
    refs = _state_keys_in_instruction(reasoning_agent.instruction)
    # reasoning runs after retrieval only.
    assert refs <= {"retrieval_output"}


def test_reflection_references_only_upstream_state_keys() -> None:
    refs = _state_keys_in_instruction(reflection_agent.instruction)
    # reflection runs after retrieval AND reasoning.
    assert refs <= {"retrieval_output", "reasoning_output"}


def test_memory_update_references_only_upstream_state_keys() -> None:
    refs = _state_keys_in_instruction(memory_update_agent.instruction)
    assert refs <= {
        "retrieval_output",
        "reasoning_output",
        "reflection_output",
    }


# ---------- tool wiring ----------


def test_retrieval_agent_has_retrieve_incidents_tool() -> None:
    tool_names = {_tool_name(t) for t in retrieval_agent.tools}
    assert "retrieve_incidents" in tool_names


def test_reflection_agent_has_record_reflection_tool() -> None:
    tool_names = {_tool_name(t) for t in reflection_agent.tools}
    assert "record_reflection" in tool_names


def test_memory_update_agent_has_apply_reflection_tool() -> None:
    tool_names = {_tool_name(t) for t in memory_update_agent.tools}
    assert "apply_reflection_to_memory" in tool_names


def test_reasoning_agent_has_no_tools() -> None:
    """Reasoning is a pure LLM step. Adding tools here would let it
    short-circuit the pipeline (e.g. re-retrieve), defeating the
    architecture."""
    assert reasoning_agent.tools == []


def _tool_name(tool: object) -> str:
    """Extract a stable name from an ADK tool, regardless of whether
    it was passed as a raw function or wrapped in `FunctionTool`."""
    name_attr = getattr(tool, "name", None)
    if isinstance(name_attr, str):
        return name_attr
    func = getattr(tool, "func", None)
    if func is not None and hasattr(func, "__name__"):
        return func.__name__
    return getattr(tool, "__name__", repr(tool))
