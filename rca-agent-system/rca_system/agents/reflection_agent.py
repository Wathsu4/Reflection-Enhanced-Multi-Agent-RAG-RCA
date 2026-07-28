"""Reflection sub-agent.

Stage 3 of the RCA pipeline. A skeptical second opinion: reads the
hypothesis from the reasoning stage and decides which retrieved
incidents actually helped, which were noise, and how confident we
should be overall.

Tier 0 Phase 4 (How-To-Improve/TIER0_PLAN.md) replaced the single-shot
judgment call with `ensemble_reflect`, which internally fans out
`settings.reflection_ensemble_size` independent, concurrent Gemini
samples and aggregates them (reduces single-sample noise in the
reflection signal). This agent's own visible turn is now a thin
dispatcher: call the tool once, echo its result. All the actual
judgment happens inside the tool.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from rca_system.settings import settings
from rca_system.tools.reflection_ensemble import ensemble_reflect

_ensemble_reflect_tool = FunctionTool(func=ensemble_reflect)

reflection_agent = Agent(
    name="reflection_agent",
    model=settings.gemini_model,
    description=(
        "Third stage of the RCA pipeline: critiques the reasoning agent's "
        "hypothesis and assigns relevance deltas to each retrieved incident, "
        "by sampling and aggregating multiple independent judgments."
    ),
    instruction=(
        "Step 1. Call the `ensemble_reflect` tool ONCE. It takes no "
        "arguments -- it reads the retrieval results and the reasoning "
        "agent's hypothesis directly from state, and independently "
        "samples and aggregates multiple reflection judgments internally. "
        "DO NOT skip the tool call. Without it, downstream stages will "
        "have no input.\n"
        "\n"
        "Step 2. After the tool returns, output the SAME JSON object the "
        "tool returned (status, incident_score_deltas, overall_quality, "
        "rationale) and nothing else. No code fences, no extra prose."
    ),
    tools=[_ensemble_reflect_tool],
    output_key="reflection_output",
)
