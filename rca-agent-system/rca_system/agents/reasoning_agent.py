"""Reasoning sub-agent.

Stage 2 of the RCA pipeline. Reads the retrieval JSON from
`session.state["retrieval_output"]` and the original user message, then
produces a structured root-cause hypothesis.

This agent has no tools -- it's a pure reasoning step. Its output is
consumed by the reflection agent.
"""

from __future__ import annotations

from google.adk.agents import Agent

from rca_system.settings import settings

reasoning_agent = Agent(
    name="reasoning_agent",
    model=settings.gemini_model,
    description=(
        "Second stage of the RCA pipeline: generates a root-cause hypothesis "
        "from the retrieved past incidents and the original log chunk."
    ),
    # The `?` suffix on `{retrieval_output?}` makes the template
    # substitution defensive -- if the retrieval stage failed to write
    # state (e.g. the LLM skipped the tool call), the placeholder
    # collapses to an empty string instead of raising at runtime.
    instruction=(
        "You are a senior SRE performing root-cause analysis.\n"
        "\n"
        "Inputs available to you:\n"
        "  * The original log chunk: it appears in the user message above.\n"
        "  * Retrieval results (JSON, may be empty): {retrieval_output?}\n"
        "\n"
        "Produce a SINGLE JSON object with EXACTLY these keys and nothing "
        "else:\n"
        "  hypothesis (string): one paragraph describing the most likely "
        "    root cause. Cite the incident_ids you leaned on, e.g. "
        '    "consistent with redis-conn-refused-001". If you used no '
        "    retrieved incidents, say so.\n"
        "  confidence (number, 0-1): your honest confidence in the "
        "    hypothesis. Below 0.5 means the retrieval did not help much.\n"
        "  suggested_actions (array of 2-4 strings): concrete next steps "
        "    for the on-call engineer. Each step is one short sentence.\n"
        "  evidence (array of strings): up to 5 short quotes -- log lines "
        "    or facts from retrieved incidents -- that support the "
        "    hypothesis.\n"
        "  used_incident_ids (array of strings): the incident_ids that "
        "    actually informed your reasoning (subset of those in the "
        "    retrieval JSON; may be empty).\n"
        "\n"
        "Critical formatting rules:\n"
        "- Output the JSON only. No prose before or after.\n"
        "- Do NOT wrap in markdown code fences.\n"
        "- If the retrieval JSON is empty or clearly irrelevant, still "
        "  produce the JSON: write the hypothesis you can defend from the "
        "  log chunk alone, set confidence below 0.5, and leave "
        "  used_incident_ids as []."
    ),
    output_key="reasoning_output",
)
