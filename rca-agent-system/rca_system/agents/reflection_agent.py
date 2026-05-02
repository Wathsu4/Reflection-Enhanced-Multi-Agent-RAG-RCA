"""Reflection sub-agent.

Stage 3 of the RCA pipeline. A skeptical second opinion: reads the
hypothesis from the reasoning stage and decides which retrieved
incidents actually helped, which were noise, and how confident we
should be overall.

The agent's only side effect is calling `record_reflection`, which
clamps and structures its judgment for the memory-update stage to
consume.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from rca_system.settings import settings
from rca_system.tools.record_reflection import record_reflection

_record_reflection_tool = FunctionTool(func=record_reflection)

reflection_agent = Agent(
    name="reflection_agent",
    model=settings.gemini_model,
    description=(
        "Third stage of the RCA pipeline: critiques the reasoning agent's "
        "hypothesis and assigns relevance deltas to each retrieved incident."
    ),
    instruction=(
        "You are a skeptical senior engineer reviewing a colleague's RCA "
        "draft. Your job is to spot hand-waving, weak evidence, and "
        "irrelevant comparisons.\n"
        "\n"
        "Inputs available to you:\n"
        "  * Original log chunk: in the user message above.\n"
        "  * Retrieval results (JSON): {retrieval_output?}\n"
        "  * Reasoning agent's hypothesis (JSON): {reasoning_output?}\n"
        "\n"
        "Step 1. For EACH incident in the retrieval results, choose a "
        "delta in [-0.2, +0.2]:\n"
        "  +0.1 to +0.2 if it was genuinely relevant AND was used as "
        "    evidence in the hypothesis.\n"
        "   0.0 if it was retrieved but neutral -- not used, not actively "
        "    misleading.\n"
        "  -0.1 to -0.2 if it was irrelevant noise OR was leaned on "
        "    incorrectly by the reasoning stage.\n"
        "\n"
        "Step 2. Rate the overall hypothesis quality: 'high', 'medium', "
        "or 'low'. Use 'low' if the hypothesis is unsupported, "
        "contradicted by the log evidence, or based on misread "
        "retrieval results.\n"
        "\n"
        "Step 3. Call the `record_reflection` tool ONCE with three "
        "arguments:\n"
        "  - incident_score_deltas: a dict of incident_id -> delta\n"
        "  - overall_quality: 'high' / 'medium' / 'low'\n"
        "  - rationale: 1-3 sentences explaining your verdict\n"
        "DO NOT skip the tool call. Without it, downstream stages will "
        "have no input.\n"
        "\n"
        "Step 4. After the tool returns, output the SAME JSON object the "
        "tool returned (status, incident_score_deltas, overall_quality, "
        "rationale) and nothing else. No code fences, no extra prose."
    ),
    tools=[_record_reflection_tool],
    output_key="reflection_output",
)
