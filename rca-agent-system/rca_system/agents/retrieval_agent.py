"""Retrieval sub-agent.

A specialist LLM whose only job is to call the `retrieve_incidents`
tool with a well-formed query and present the results. Phase 7 will
plug this into a `SequentialAgent` pipeline; for now we expose it
directly via `root_agent` so we can smoke-test retrieval end-to-end
through the ADK HTTP surface.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from rca_system.settings import settings
from rca_system.tools.retrieve_incidents import retrieve_incidents

# Wrap explicitly. ADK accepts plain functions in `tools=[...]` and
# lazy-wraps them, but going through `FunctionTool` makes it obvious
# what's being exposed and what the tool's name will be.
_retrieve_incidents_tool = FunctionTool(func=retrieve_incidents)

retrieval_agent = Agent(
    name="retrieval_agent",
    model=settings.gemini_model,
    description=(
        "Retrieves the most relevant past incidents from the knowledge base. "
        "Use this when the user describes a new incident or pastes a log "
        "chunk and wants to see similar resolved cases."
    ),
    instruction=(
        "You are a retrieval specialist for an SRE knowledge base.\n"
        "\n"
        "When given a log chunk or incident description:\n"
        "1. Pull out the most informative search terms -- error messages, "
        "component names, error codes, symptom keywords. Ignore timestamps "
        "and noise.\n"
        "2. Call the `retrieve_incidents` tool with that focused query "
        "(typically k=5).\n"
        "3. Present the returned hits as a numbered Markdown list. For each "
        "hit show: incident_id, title, severity, root_cause, similarity, "
        "and success_score.\n"
        "4. AFTER the list, in a single closing sentence: if the FIRST hit's "
        "similarity is below 0.4, warn that no past incident closely matches; "
        "otherwise say nothing. Do not annotate individual hits with this "
        "warning -- only the overall result set.\n"
        "\n"
        "Do NOT fabricate incidents. Only report what the tool returned. "
        "Do NOT speculate about the root cause yet -- that's a downstream "
        "agent's job."
    ),
    tools=[_retrieve_incidents_tool],
)
