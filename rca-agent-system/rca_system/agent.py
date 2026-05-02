"""Top-level `root_agent` for the RCA system.

Phase 7: a four-stage `SequentialAgent` pipeline.

    user log chunk
        |
        v
    [retrieval_agent]    ----> session.state["retrieval_output"]   (JSON)
        |
        v
    [reasoning_agent]    ----> session.state["reasoning_output"]   (JSON)
        |
        v
    [reflection_agent]   ----> session.state["reflection_output"]  (JSON)
        |
        v
    [memory_update_agent] --> session.state["final_output"]        (Markdown)
        |
        v
    final markdown response surfaced to the user

State propagates between stages via `output_key` writes from each
sub-agent and `{state_key}` template substitutions in downstream
instructions (handled automatically by ADK's `inject_session_state`).

ADK discovers this agent by importing the `rca_system` package and
looking for the symbol `root_agent` (re-exported from `__init__.py`).
"""

from __future__ import annotations

from google.adk.agents import SequentialAgent

from rca_system.agents.memory_update_agent import memory_update_agent
from rca_system.agents.reasoning_agent import reasoning_agent
from rca_system.agents.reflection_agent import reflection_agent
from rca_system.agents.retrieval_agent import retrieval_agent

# Order matters here: each agent reads outputs written by all previous
# agents in the list. Reordering is a breaking change to the contract.
root_agent = SequentialAgent(
    name="rca_root_agent",
    description=(
        "Root-cause analysis pipeline for software incidents. Retrieves "
        "similar past incidents, generates a hypothesis, reflects on it, "
        "and updates the knowledge base based on the reflection."
    ),
    sub_agents=[
        retrieval_agent,
        reasoning_agent,
        reflection_agent,
        memory_update_agent,
    ],
)
