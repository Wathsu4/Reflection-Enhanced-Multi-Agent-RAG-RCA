"""Verifies the ADK agent module is importable and the symbol contract
ADK relies on (`root_agent` re-exported from the package) is intact.

These tests do NOT call Gemini -- they just exercise the static plumbing.
A separate live test (skipped by default) covers the API call.
"""

from __future__ import annotations

import rca_system
from rca_system.agent import root_agent as direct
from rca_system.settings import settings


def test_root_agent_reexported_from_package() -> None:
    # ADK discovers agents by importing the package and looking for this
    # symbol; if this assertion fails, `adk web` and `get_fast_api_app`
    # will silently miss our agent.
    assert hasattr(rca_system, "root_agent")
    assert rca_system.root_agent is direct


def test_root_agent_uses_settings_model() -> None:
    """The root agent's identity may change across phases (Phase 5: a
    placeholder; Phase 6: the retrieval specialist; Phase 7: a
    SequentialAgent). What MUST stay stable is that the model name comes
    from settings, not a hardcoded constant -- that's the contract that
    keeps the env-var override working."""
    # SequentialAgent (Phase 7) won't have a `.model` attribute. Skip
    # the assertion gracefully when that day comes; until then we want
    # this check to actually fire.
    if hasattr(direct, "model"):
        assert direct.model == settings.gemini_model


def test_root_agent_has_a_nonempty_description() -> None:
    """Every agent (including SequentialAgent orchestrators) has a
    description -- it's how Gemini decides whether to delegate to a
    sub-agent in hierarchical setups, and how `adk web` labels the
    pipeline. An empty description silently degrades both."""
    assert isinstance(direct.description, str)
    assert len(direct.description.strip()) > 30


def test_llm_root_agent_has_a_nonempty_instruction() -> None:
    """Phase 5 / Phase 6: root_agent was an LLM `Agent`; instruction
    must be present. Phase 7: root_agent is a SequentialAgent which
    has no `instruction` field at all -- skip the check."""
    if hasattr(direct, "instruction"):
        instruction = direct.instruction
        assert isinstance(instruction, str)
        assert len(instruction.strip()) > 50
