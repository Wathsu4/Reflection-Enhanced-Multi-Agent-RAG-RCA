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
from google.genai import types as genai_types

from rca_system.settings import settings
from rca_system.tools.record_reflection import record_reflection


class _RecordReflectionTool(FunctionTool):
    """`FunctionTool` for `record_reflection` with a hand-built parameter
    schema -- works around a google-adk bug (google/adk-python#5364).

    `record_reflection`'s Python signature declares
    `used_incident_ids`/`retrieved_incident_ids` as `list[str] | None =
    None` so direct callers (unit tests, back-compat) can omit them. But
    ADK's automatic schema builder falls back to
    `pydantic.TypeAdapter(...).json_schema()` for any function with an
    `Optional[list[str]]`-shaped parameter, which emits a snake_case
    `additional_properties` key instead of the Gemini API's expected
    `additionalProperties` -- gemini-2.5-flash 400s on the unrecognized
    field (gemini-*-pro tolerates it silently, which is why this is easy
    to miss). The fallback is also contagious: it corrupts sibling
    parameters in the *same* schema, e.g. `incident_score_deltas`'s
    otherwise-fine `dict[str, float]` schema gets the same broken
    treatment even though that parameter never changed.

    The reflection agent's instruction always supplies concrete lists for
    the two new params (never omits, never sends null), so declaring them
    required here matches actual usage. ADK invokes the real
    `record_reflection` function regardless of this declared schema, so
    if a model ever omits them anyway, the call still falls back safely
    to `record_reflection`'s own `None` default (gate disabled).
    """

    def _get_declaration(self) -> genai_types.FunctionDeclaration | None:
        return genai_types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "incident_score_deltas": genai_types.Schema(
                        type=genai_types.Type.OBJECT
                    ),
                    "overall_quality": genai_types.Schema(type=genai_types.Type.STRING),
                    "rationale": genai_types.Schema(type=genai_types.Type.STRING),
                    "used_incident_ids": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.STRING),
                    ),
                    "retrieved_incident_ids": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.STRING),
                    ),
                },
                required=[
                    "incident_score_deltas",
                    "overall_quality",
                    "rationale",
                    "used_incident_ids",
                    "retrieved_incident_ids",
                ],
            ),
        )


_record_reflection_tool = _RecordReflectionTool(func=record_reflection)

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
        "Step 1. For EACH incident in the retrieval results, decide "
        "whether it earns a delta in [-0.2, +0.2]:\n"
        "  +0.1 to +0.2 ONLY if it appears in the hypothesis's "
        "    used_incident_ids AND you agree it was genuinely relevant. "
        "    A downstream gate silently drops any positive delta for an "
        "    incident that was not actually cited as used, so don't "
        "    bother proposing one otherwise.\n"
        "  -0.1 to -0.2 if it was irrelevant noise OR was leaned on "
        "    incorrectly by the reasoning stage. You MUST name this "
        "    incident in your rationale and say why.\n"
        "  OMIT the incident entirely (do not add its id to "
        "    incident_score_deltas) if it's merely neutral -- retrieved "
        "    but neither clearly helpful nor clearly misleading. IF IN "
        "    DOUBT, OMIT IT: neutral evidence must not move the score in "
        "    either direction. Only a small, bounded number of negative "
        "    deltas are honored per call, so reserve them for incidents "
        "    you are genuinely confident were misleading.\n"
        "\n"
        "Step 2. Rate the overall hypothesis quality: 'high', 'medium', "
        "or 'low'. Use 'low' if the hypothesis is unsupported, "
        "contradicted by the log evidence, or based on misread "
        "retrieval results.\n"
        "\n"
        "Step 3. Call the `record_reflection` tool ONCE with FIVE "
        "arguments:\n"
        "  - incident_score_deltas: a dict of incident_id -> delta "
        "    (omitted incidents are simply absent from this dict)\n"
        "  - overall_quality: 'high' / 'medium' / 'low'\n"
        "  - rationale: 1-3 sentences explaining your verdict; name any "
        "    incident you assigned a negative delta to\n"
        "  - used_incident_ids: copy the used_incident_ids array "
        "    verbatim from the reasoning agent's hypothesis JSON above "
        "    (empty list if it used none)\n"
        "  - retrieved_incident_ids: the incident_id of every hit in "
        "    the retrieval results JSON above (empty list if there were "
        "    none)\n"
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
