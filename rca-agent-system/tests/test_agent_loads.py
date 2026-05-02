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


def test_root_agent_has_expected_identity() -> None:
    assert direct.name == "rca_root_agent"
    # The model must come from settings -- if a future refactor hardcodes
    # "gemini-1.5-flash" here, the env-var override stops working.
    assert direct.model == settings.gemini_model


def test_root_agent_has_a_nonempty_instruction() -> None:
    # ADK accepts `instruction` as a string OR a callable. We use the
    # string form; this just guards against accidental empty prompts.
    instruction = direct.instruction
    assert isinstance(instruction, str)
    assert len(instruction.strip()) > 50
