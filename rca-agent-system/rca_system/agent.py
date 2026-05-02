"""Top-level `root_agent` for the RCA system.

Phase 5 ships a placeholder: a single LLM agent with no tools. The point
of this phase is to verify the plumbing -- ADK loads our agent, Gemini
auth works, FastAPI serves -- *not* to do real RCA. Phase 7 replaces this
file with a SequentialAgent that wires together retrieval, reasoning,
reflection, and memory-update sub-agents.

ADK discovers this agent by importing the `rca_system` package and
looking for the symbol `root_agent` (re-exported from `__init__.py`).
"""

from __future__ import annotations

from google.adk.agents import Agent

from rca_system.settings import settings

PLACEHOLDER_INSTRUCTION = (
    "You are an expert SRE assistant helping diagnose software incidents. "
    "When given a log chunk, briefly describe what you think is going wrong "
    "and what an on-call engineer should investigate first. "
    "Keep your answer to one paragraph; cite specific log lines when useful. "
    "In a future phase you will be replaced by a multi-agent pipeline that "
    "retrieves prior incidents and self-critiques its hypothesis -- for now, "
    "answer directly."
)

root_agent = Agent(
    name="rca_root_agent",
    model=settings.gemini_model,
    description="Root orchestrator for root-cause analysis of software incidents.",
    instruction=PLACEHOLDER_INSTRUCTION,
)
