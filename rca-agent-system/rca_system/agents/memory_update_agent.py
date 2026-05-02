"""Memory-update sub-agent.

Stage 4 (final) of the RCA pipeline. Two responsibilities:
  1. Apply the reflection agent's clamped score deltas to ChromaDB by
     calling `apply_reflection_to_memory`.
  2. Render the final user-facing markdown report combining all upstream
     stages' outputs.

This is the only stage whose textual output is meant for the human
operator -- everything before it produced JSON for inter-agent
plumbing.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from rca_system.settings import settings
from rca_system.tools.update_memory import apply_reflection_to_memory

_apply_reflection_tool = FunctionTool(func=apply_reflection_to_memory)

memory_update_agent = Agent(
    name="memory_update_agent",
    model=settings.gemini_model,
    description=(
        "Final stage of the RCA pipeline: persists reflection-driven score "
        "updates to the knowledge base and produces the user-facing summary."
    ),
    instruction=(
        "You are the final stage of an RCA pipeline. Your job is to "
        "persist memory updates and produce a clean operator-ready "
        "summary.\n"
        "\n"
        "Inputs available to you:\n"
        "  * Reasoning agent's hypothesis (JSON): {reasoning_output?}\n"
        "  * Reflection agent's verdict (JSON): {reflection_output?}\n"
        "\n"
        "Step 1. From the reflection JSON, extract the "
        "`incident_score_deltas` field. Call the "
        "`apply_reflection_to_memory` tool ONCE with that dict as its "
        "argument. Do not skip this call -- the dynamic-memory contract "
        "depends on it. If `incident_score_deltas` is empty, still call "
        "the tool with an empty dict so the rest of the pipeline can "
        "verify the call happened.\n"
        "\n"
        "Step 2. After the tool returns, write the final operator "
        "summary as Markdown. Use EXACTLY these four section headers, "
        "in this order, each as a level-2 heading:\n"
        "\n"
        "## Root cause\n"
        "  Restate the reasoning agent's hypothesis in 1-3 sentences. "
        "Include the cited incident_ids inline.\n"
        "\n"
        "## Suggested actions\n"
        "  A bulleted list of the suggested_actions from the reasoning "
        "JSON, lightly polished. One bullet per action.\n"
        "\n"
        "## Confidence & caveats\n"
        "  State the reasoning agent's confidence (e.g. 'Confidence: "
        "0.78') and the reflection agent's overall_quality verdict in "
        "one paragraph. If reflection rated the hypothesis 'low', open "
        "with a clear warning.\n"
        "\n"
        "## Memory updates\n"
        "  One bullet per incident in the tool's `updated` field, "
        "formatted as: '`<incident_id>`: <old_score> -> <new_score> "
        "(\u0394 <delta>)'. If `updated` is empty, write 'No memory "
        "changes applied.'\n"
        "\n"
        "Output ONLY the Markdown summary. No JSON, no code fences."
    ),
    tools=[_apply_reflection_tool],
    output_key="final_output",
)
