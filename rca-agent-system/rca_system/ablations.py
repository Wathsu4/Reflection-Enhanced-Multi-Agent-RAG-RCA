"""Ablation / baseline pipeline factory for the evaluation harness.

The thesis defense needs ablation studies and baseline comparisons
(see `How-To-Evaluate/PLAN.md`, Families 1 & 2). Every variant below is
a *prompt / wiring* change only -- no re-training, no model swap -- so
they all run on the same seeded ChromaDB and the same Gemini model.

`build_root_agent(ablation)` returns the ADK agent to run for a given
variant, **or `None`** for the deterministic `retrieval_only` baseline
(which performs no LLM call and is handled directly by the eval script).

Variants
--------
none            Full 4-agent pipeline (the system under test). Imports the
                production `root_agent` verbatim.
reflection_off  retrieval -> reasoning -> memory_update. No reflection
                stage, so memory_update receives no deltas and the
                knowledge base is never mutated. (E1.1)
memory_frozen   Full pipeline, but the memory_update stage uses a *frozen*
                apply tool that reports would-be changes WITHOUT writing
                to ChromaDB -- success_score stays 1.0 forever. (E1.2)
no_rag          reasoning -> memory_update with NO retrieval stage. The
                reasoning agent sees an empty `retrieval_output` and must
                diagnose from the raw log chunk alone. (E1.4)
cot_only        Architecturally identical to `no_rag`; kept as a separate
                label so the results table can frame it as a *baseline*
                (E2.2) rather than an ablation.
retrieval_only  Deterministic top-k retrieval, no LLM. Returns `None`
                here; `scripts/evaluate.py` synthesises the report from
                the top hit. The zero-hallucination floor baseline. (E2.1)

Parent-conflict note: ADK enforces that an `Agent` has at most one
parent. The production `root_agent` already claims the shared sub-agent
singletons as its children, so an ablation pipeline cannot reuse those
same instances. Every ablation branch therefore builds **fresh clones**
of the sub-agents via `_clone_agent`; this also makes `build_root_agent`
idempotent (safe to call repeatedly, e.g. in tests).
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import FunctionTool

from rca_system.settings import settings

logger = logging.getLogger(__name__)


def _clone_agent(agent: Agent, **overrides: Any) -> Agent:
    """Return a fresh, parent-free copy of an LLM `Agent`.

    Copies the fields our sub-agents actually set (name, model,
    description, instruction, tools, output_key). Tool instances are
    shared by reference -- tools have no single-parent constraint -- so
    only the agent wrapper is duplicated. `overrides` replace any field.
    """
    fields: dict[str, Any] = {
        "name": agent.name,
        "model": agent.model,
        "description": agent.description,
        "instruction": agent.instruction,
        "tools": list(getattr(agent, "tools", []) or []),
        "output_key": agent.output_key,
    }
    fields.update(overrides)
    return Agent(**fields)

# Canonical list of supported ablation/baseline identifiers. The eval
# scripts expose this verbatim as the `--ablation` choices.
ABLATIONS: tuple[str, ...] = (
    "none",
    "reflection_off",
    "memory_frozen",
    "no_rag",
    "cot_only",
    "retrieval_only",
    "react",
)

# Variants that perform no LLM call and so have no ADK agent to run.
DETERMINISTIC_ABLATIONS: frozenset[str] = frozenset({"retrieval_only"})


def _apply_reflection_to_memory_frozen(
    incident_score_deltas: dict[str, float],
) -> dict[str, Any]:
    """Frozen twin of `apply_reflection_to_memory`.

    Reports the deltas the reflection agent proposed but performs NO
    write to ChromaDB, so `success_score` never moves. This isolates the
    *score-mutation mechanism* (E1.2): reflection still runs and produces
    a signal, but the loop is severed at the persistence step.
    """
    if not isinstance(incident_score_deltas, dict):
        logger.warning(
            "Ignoring incident_score_deltas of unsupported type %s",
            type(incident_score_deltas).__name__,
        )
        return {"updated": {}, "skipped": {}, "frozen": True}

    results: dict[str, dict[str, float]] = {}
    skipped: dict[str, str] = {}
    for incident_id, raw_delta in incident_score_deltas.items():
        try:
            delta = float(raw_delta)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping incident %r: non-numeric delta %r", incident_id, raw_delta
            )
            skipped[str(incident_id)] = "invalid_delta"
            continue
        # new == old: the write is intentionally suppressed.
        results[str(incident_id)] = {
            "old_score": 1.0,
            "new_score": 1.0,
            "delta": round(delta, 3),
        }
    return {"updated": results, "skipped": skipped, "frozen": True}


def _build_memory_update_agent_frozen() -> Agent:
    """A memory_update stage whose persistence tool is a no-op.

    Mirrors `rca_system.agents.memory_update_agent` but swaps the apply
    tool for the frozen variant above. The instruction is copied verbatim
    so the rendered report is comparable to the real pipeline's.
    """
    from rca_system.agents.memory_update_agent import memory_update_agent

    return Agent(
        name="memory_update_agent_frozen",
        model=settings.gemini_model,
        description=memory_update_agent.description,
        instruction=memory_update_agent.instruction,
        tools=[FunctionTool(func=_apply_reflection_to_memory_frozen)],
        output_key="final_output",
    )


# ---- ReAct (Reason + Act) single-agent baseline ----
# A standard agentic baseline: Yao et al. 2022 (arXiv:2210.03629); the design
# Roy et al. (FSE'24, Microsoft, arXiv:2403.04123) evaluate for RCA; and the
# predecessor that Reflexion (Shinn et al. 2023) -- which our reflection +
# memory design descends from -- builds on. It interleaves reasoning with
# adaptive tool calls in a single agent, with NO fixed pipeline, NO reflection,
# and NO cross-incident memory, so it isolates "adaptive single agent" from our
# "multi-agent + reflection + memory" approach.

# Hard cap on retrieve_incidents calls per run: bounds cost and prevents a
# runaway reason-act loop. Belt-and-suspenders with the instruction's limit.
_REACT_MAX_TOOL_CALLS = 3

_REACT_INSTRUCTION = (
    "You are an autonomous SRE root-cause-analysis agent using the ReAct "
    "(Reason + Act) strategy. You operate in a loop: THINK about what the "
    "symptoms suggest, optionally ACT by calling a tool to gather evidence, "
    "OBSERVE the result, and repeat until you can confidently explain the "
    "incident.\n"
    "\n"
    "Tool available:\n"
    "  retrieve_incidents(query, k): semantic search over a knowledge base of "
    "past incidents. Returns hits with incident_id, title, root_cause, "
    "resolution, similarity, and success_score.\n"
    "\n"
    "How to operate:\n"
    "1. Read the user's log chunk.\n"
    "2. THINK: briefly note the key symptoms (error messages, components, "
    "codes) and what evidence would help.\n"
    "3. ACT: if past incidents would help, call retrieve_incidents with a "
    "focused query. If the first results are weak, you may refine the query "
    "and call again -- but call it AT MOST 3 times in total.\n"
    "4. OBSERVE the returned incidents; decide whether you have enough.\n"
    "5. When confident (or once retrieval is exhausted), STOP calling tools "
    "and write the final report.\n"
    "\n"
    "Final report -- output ONLY this Markdown, using EXACTLY these three "
    "level-2 headings, in this order:\n"
    "\n"
    "## Root cause\n"
    "  1-3 sentences naming the most likely root cause. Cite any incident_ids "
    "you relied on inline (e.g. 'consistent with redis-conn-refused-001'). If "
    "retrieval did not help, say so and diagnose from the log alone.\n"
    "\n"
    "## Suggested actions\n"
    "  2-4 concrete next steps for the on-call engineer, as a bulleted list.\n"
    "\n"
    "## Confidence & caveats\n"
    "  One short paragraph: your confidence and any uncertainty.\n"
    "\n"
    "Do not invent details that are not supported by the log or the retrieved "
    "incidents."
)


def _react_tool_call_cap(tool: Any, args: dict[str, Any], tool_context: Any) -> Any:
    """`before_tool_callback` enforcing `_REACT_MAX_TOOL_CALLS`.

    Returns `None` to allow the call; once the budget is spent it short-
    circuits the tool with an empty result that tells the agent to answer
    now (so a misbehaving model can't loop indefinitely or burn quota).
    """
    used = int(tool_context.state.get("_react_tool_calls", 0))
    if used >= _REACT_MAX_TOOL_CALLS:
        return {
            "hits": [],
            "note": (
                f"Retrieval budget of {_REACT_MAX_TOOL_CALLS} calls exhausted. "
                "Do not call retrieve_incidents again; write your final report now."
            ),
        }
    tool_context.state["_react_tool_calls"] = used + 1
    return None


def build_react_agent() -> Agent:
    """Single ReAct agent: same model + retrieval tool + KB as the full
    system, but it decides when/whether to retrieve and writes the report
    itself. No reflection, no memory writes. Output obeys the same report
    contract so it scores on the same metrics."""
    from rca_system.tools.retrieve_incidents import retrieve_incidents

    return Agent(
        name="rca_react_agent",
        model=settings.gemini_model,
        description=(
            "ReAct single-agent baseline: interleaves reasoning with adaptive "
            "retrieval, then writes the RCA report."
        ),
        instruction=_REACT_INSTRUCTION,
        tools=[FunctionTool(func=retrieve_incidents)],
        before_tool_callback=_react_tool_call_cap,
        output_key="final_output",
    )


def build_root_agent(ablation: str = "none") -> Any:
    """Return the agent to run for `ablation`, or `None` for deterministic
    baselines (`retrieval_only`).

    Raises `ValueError` for unknown identifiers.
    """
    if ablation not in ABLATIONS:
        raise ValueError(
            f"unknown ablation {ablation!r}; choose from {', '.join(ABLATIONS)}"
        )

    if ablation == "none":
        # Production pipeline. Importing here (not at module top) keeps the
        # shared sub-agent singletons unclaimed for the ablation branches.
        from rca_system.agent import root_agent

        return root_agent

    if ablation in DETERMINISTIC_ABLATIONS:
        return None

    if ablation == "react":
        # Single-agent ReAct baseline (not a clone of the pipeline -- a
        # different topology). Built fresh, so no single-parent conflict.
        return build_react_agent()

    # Build fresh clones of the sub-agent singletons so the ablation
    # pipeline never collides with `root_agent`'s single-parent claim.
    from rca_system.agents.memory_update_agent import memory_update_agent
    from rca_system.agents.reasoning_agent import reasoning_agent
    from rca_system.agents.reflection_agent import reflection_agent
    from rca_system.agents.retrieval_agent import retrieval_agent

    if ablation == "reflection_off":
        return SequentialAgent(
            name="rca_reflection_off",
            description="Ablation E1.1: retrieval + reasoning, no reflection.",
            sub_agents=[
                _clone_agent(retrieval_agent),
                _clone_agent(reasoning_agent),
                _clone_agent(memory_update_agent),
            ],
        )

    if ablation == "memory_frozen":
        return SequentialAgent(
            name="rca_memory_frozen",
            description="Ablation E1.2: full pipeline, score writes suppressed.",
            sub_agents=[
                _clone_agent(retrieval_agent),
                _clone_agent(reasoning_agent),
                _clone_agent(reflection_agent),
                _build_memory_update_agent_frozen(),
            ],
        )

    if ablation in ("no_rag", "cot_only"):
        return SequentialAgent(
            name=f"rca_{ablation}",
            description=(
                "Ablation E1.4 / baseline E2.2: reasoning from the raw log "
                "chunk alone, no retrieval."
            ),
            sub_agents=[
                _clone_agent(reasoning_agent),
                _clone_agent(memory_update_agent),
            ],
        )

    # Unreachable -- the membership check above is exhaustive.
    raise ValueError(ablation)  # pragma: no cover
