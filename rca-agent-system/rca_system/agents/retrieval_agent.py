"""Retrieval sub-agent.

Phase 6 used this agent in standalone mode (markdown output for direct
consumption). Phase 7 wires it as the FIRST stage of a 4-stage
SequentialAgent pipeline, so its output is now consumed by the
reasoning agent via `{retrieval_output}` template substitution.

That changes the contract: instead of human-readable markdown, the
agent must emit a single JSON object with a `hits` array, parseable
without code-fence stripping.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from rca_system.settings import settings
from rca_system.tools.retrieve_incidents import retrieve_incidents

# Wrap explicitly. Going through `FunctionTool` makes it obvious what's
# being exposed and what the tool's name will be.
_retrieve_incidents_tool = FunctionTool(func=retrieve_incidents)

retrieval_agent = Agent(
    name="retrieval_agent",
    model=settings.gemini_model,
    description=(
        "First stage of the RCA pipeline: retrieves the most relevant past "
        "incidents from the knowledge base for the current incident."
    ),
    instruction=(
        "You are the retrieval stage of an SRE root-cause-analysis pipeline.\n"
        "\n"
        "Step 1. Read the user's log chunk or incident description.\n"
        "Step 2. Pull out the most informative search terms -- error "
        "messages, component names, error codes, symptom keywords. Ignore "
        "timestamps and noise.\n"
        "Step 3. Call the `retrieve_incidents` tool ONCE with that focused "
        "query and k=5. Do not call it multiple times.\n"
        "Step 4. After the tool returns, output a SINGLE JSON object and "
        "nothing else. The JSON must have the exact shape:\n"
        "  {\n"
        '    "query": "<the query you sent to the tool>",\n'
        '    "hits": [<the tool\'s "hits" array verbatim>]\n'
        "  }\n"
        "\n"
        "Critical formatting rules:\n"
        "- Output the JSON only. No prose before or after.\n"
        "- Do NOT wrap the JSON in markdown code fences (no ```json).\n"
        "- Preserve every field of every hit exactly as the tool returned it; "
        "do not summarise, abbreviate, or re-order keys.\n"
        "- If the tool returned zero hits, output "
        '`{"query": "<your query>", "hits": []}`.'
    ),
    tools=[_retrieve_incidents_tool],
    # Stash the JSON in session.state["retrieval_output"] so downstream
    # sub-agents can reference it via `{retrieval_output}` substitution.
    output_key="retrieval_output",
)
