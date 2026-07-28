"""ADK function tool: multi-sample reflection ensembling (Tier 0 Phase 4).

Reduces single-sample noise in the reflection signal -- a limitation
`docs/DEFENSE_GUIDE.md` already names -- by issuing
`settings.reflection_ensemble_size` independent, concurrent Gemini
judgments of the SAME reasoning/retrieval output, gating each one
individually (Phase 1's rule, `record_reflection._gate_deltas`), and
aggregating before anything is persisted.

Design note (see How-To-Improve/TIER0_PLAN.md Phase 4 for the full
write-up): this tool takes NO Gemini-supplied arguments -- it reads
`retrieval_output`/`reasoning_output` straight from session state via
`ToolContext`, and the original log chunk from the invocation's user
content. That sidesteps a whole class of "Gemini mis-transcribed a
large JSON blob into a tool argument" bugs, and as a side effect
produces an empty JSON-schema `parameters` object for this tool --
immune to the `additional_properties` schema bug documented in
`reflection_agent.py`.

`reflection_agent`'s single visible turn now just triggers this tool
once and echoes its result -- all the actual judgment happens in the
`reflection_ensemble_size` samples fanned out here. This keeps
`reflection_agent` a plain `Agent` (same slot, same output_key, same
position in `root_agent.sub_agents`) -- `record_reflection` itself,
and every test that calls it directly, is untouched.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from google import genai
from google.adk.tools.tool_context import ToolContext
from google.genai import types as genai_types

from rca_system.settings import settings
from rca_system.tools.record_reflection import (
    _gate_deltas,
    _normalize_and_clamp_deltas,
    _normalize_id_list,
    _normalize_quality,
)

# Lower = more conservative. Used to break `overall_quality` ties toward
# the more conservative label (TIER0_PLAN.md SS4: "low > medium > high
# in a tie").
_QUALITY_CONSERVATISM = {"low": 0, "medium": 1, "high": 2}

_SAMPLE_PROMPT = """You are a skeptical senior engineer reviewing a colleague's RCA draft. Your job is to spot hand-waving, weak evidence, and irrelevant comparisons.

Inputs:
  * Original log chunk: {log_chunk}
  * Retrieval results (JSON): {retrieval_output}
  * Reasoning agent's hypothesis (JSON): {reasoning_output}

For EACH incident in the retrieval results, decide whether it earns a delta in [-0.2, +0.2]:
  +0.1 to +0.2 ONLY if it appears in the hypothesis's used_incident_ids AND you agree it was genuinely relevant.
  -0.1 to -0.2 if it was irrelevant noise OR was leaned on incorrectly by the reasoning stage. Name it in your rationale.
  OMIT the incident entirely (do not add its id to incident_score_deltas) if it's merely neutral -- retrieved but neither clearly helpful nor clearly misleading. IF IN DOUBT, OMIT IT.

Rate the overall hypothesis quality: "high", "medium", or "low". Use "low" if the hypothesis is unsupported, contradicted by the log evidence, or based on misread retrieval results.

Respond with ONLY a single JSON object (no code fences, no prose) with EXACTLY these keys:
{{"incident_score_deltas": {{"<incident_id>": <float>, ...}}, "overall_quality": "high"|"medium"|"low", "rationale": "<1-3 sentences>", "used_incident_ids": ["<incident_id>", ...]}}"""


async def _sample_reflection(
    client: genai.Client, log_chunk: str, retrieval_output: str, reasoning_output: str
) -> tuple[dict[str, Any] | None, int]:
    """One independent Gemini sample of the reflection judgment.

    Returns `(None, 0)` on any failure (network error, timeout,
    malformed or non-JSON response) so the ensemble degrades gracefully
    over the surviving samples rather than failing the whole pipeline
    run. Otherwise returns `(parsed_dict, total_token_count)` -- these
    raw calls bypass ADK's own Runner/event stream entirely, so their
    token cost would otherwise be invisible to `scripts/evaluate.py`'s
    per-stage token accounting; surfacing it here lets the Phase 4
    "roughly 3x tokens on the reflection stage" checkpoint actually be
    measured instead of assumed.
    """
    prompt = _SAMPLE_PROMPT.format(
        log_chunk=log_chunk or "(not available)",
        retrieval_output=retrieval_output,
        reasoning_output=reasoning_output,
    )
    try:
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.7, response_mime_type="application/json"
            ),
        )
        usage = getattr(resp, "usage_metadata", None)
        tokens = int(getattr(usage, "total_token_count", 0) or 0) if usage else 0
        data = json.loads(resp.text or "")
        return (data, tokens) if isinstance(data, dict) else (None, tokens)
    except Exception:
        return None, 0


def _majority_quality(qualities: list[str]) -> str:
    """Majority vote across sample qualities; ties broken toward the
    more conservative label (low > medium > high in a tie,
    TIER0_PLAN.md SS4). Samples with an unrecognised quality don't count
    toward any vote; if none are recognised, returns "unknown"."""
    valid = [q for q in qualities if q in _QUALITY_CONSERVATISM]
    if not valid:
        return "unknown"
    counts: dict[str, int] = {}
    for q in valid:
        counts[q] = counts.get(q, 0) + 1
    top = max(counts.values())
    tied = [q for q, c in counts.items() if c == top]
    return min(tied, key=lambda q: _QUALITY_CONSERVATISM[q])


def aggregate_samples(gated_deltas_per_sample: list[dict[str, float]]) -> dict[str, float]:
    """Mean per-incident delta across samples that proposed a (post-gate
    -surviving) delta for that id; an id proposed by zero samples gets
    no entry (TIER0_PLAN.md SS4). Pure and synchronous -- independently
    unit-testable without mocking Gemini."""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for gated in gated_deltas_per_sample:
        for incident_id, delta in gated.items():
            sums[incident_id] = sums.get(incident_id, 0.0) + delta
            counts[incident_id] = counts.get(incident_id, 0) + 1
    return {incident_id: sums[incident_id] / counts[incident_id] for incident_id in sums}


def _extract_retrieved_ids(retrieval_output: Any) -> list[str]:
    """Pull the incident_id of every hit out of a retrieval_output
    payload (dict or JSON string). Empty list on any parse failure."""
    try:
        data = (
            retrieval_output
            if isinstance(retrieval_output, dict)
            else json.loads(str(retrieval_output))
        )
        hits = data.get("hits") or []
        return [str(h.get("incident_id")) for h in hits if h.get("incident_id")]
    except Exception:
        return []


async def run_ensemble(
    log_chunk: str, retrieval_output: Any, reasoning_output: Any
) -> dict[str, Any]:
    """Core async orchestration, independently testable (no `ToolContext`
    needed): issue `settings.reflection_ensemble_size` concurrent Gemini
    samples via `asyncio.gather` (wall-clock latency doesn't scale with
    ensemble size -- only token cost does), gate each sample
    individually against the SAME `retrieved_incident_ids`, then
    aggregate.

    `settings.reflection_ensemble_size == 1` degenerates to a single
    sample -- the mean-of-one and majority-vote-of-one are just that
    sample's own (gated) values -- reproducing single-shot reflection
    behavior for cheap local iteration.
    """
    n = max(1, settings.reflection_ensemble_size)
    retrieved_incident_ids = _extract_retrieved_ids(retrieval_output)
    retrieval_str = (
        retrieval_output if isinstance(retrieval_output, str) else json.dumps(retrieval_output)
    )
    reasoning_str = (
        reasoning_output if isinstance(reasoning_output, str) else json.dumps(reasoning_output)
    )

    client = genai.Client(api_key=settings.google_api_key)
    raw_results = await asyncio.gather(
        *(
            _sample_reflection(client, log_chunk, retrieval_str, reasoning_str)
            for _ in range(n)
        )
    )
    total_tokens = sum(tokens for _sample, tokens in raw_results)
    succeeded = [sample for sample, _tokens in raw_results if sample is not None]

    gated_per_sample: list[dict[str, float]] = []
    qualities: list[str] = []
    rationales: list[str] = []
    positive_dropped = 0
    negative_dropped = 0

    for sample in succeeded:
        clamped = _normalize_and_clamp_deltas(sample.get("incident_score_deltas"))
        used_ids = _normalize_id_list(sample.get("used_incident_ids"))
        gated, pos_dropped, neg_dropped = _gate_deltas(clamped, used_ids, retrieved_incident_ids)
        gated_per_sample.append(gated)
        positive_dropped += pos_dropped
        negative_dropped += neg_dropped
        qualities.append(_normalize_quality(sample.get("overall_quality")))
        rationale = str(sample.get("rationale") or "").strip()
        if rationale:
            rationales.append(rationale)

    aggregated_deltas = aggregate_samples(gated_per_sample)
    overall_quality = _majority_quality(qualities)
    agreement = (
        round(sum(1 for q in qualities if q == overall_quality) / len(qualities), 3)
        if qualities
        else 0.0
    )

    return {
        "status": "recorded",
        "incident_score_deltas": aggregated_deltas,
        "overall_quality": overall_quality,
        "rationale": " | ".join(rationales[:3]) if rationales else "",
        "_debug": {
            "positive_dropped_count": positive_dropped,
            "negative_dropped_count": negative_dropped,
            "ensemble_size": n,
            "ensemble_succeeded": len(succeeded),
            "ensemble_agreement": agreement,
            "ensemble_total_tokens": total_tokens,
        },
    }


async def ensemble_reflect(tool_context: ToolContext) -> dict[str, Any]:
    """Judge the current RCA run's reasoning by sampling multiple
    independent reflections and aggregating them, instead of trusting a
    single Gemini judgment call. Reduces single-sample noise in the
    reflection signal.

    Takes no arguments -- reads the retrieval and reasoning JSON
    straight from session state, and the original log chunk from the
    invocation's user message, so there's nothing for you to
    mis-transcribe. Just call this tool once with no arguments.

    Returns:
        A dict with the structured reflection record: status,
        incident_score_deltas, overall_quality, rationale -- same shape
        the single-sample reflection tool used to return. Also includes
        a `_debug` key with per-sample diagnostics (evaluation-only; the
        production pipeline ignores it).
    """
    state = tool_context.state
    retrieval_output = state.get("retrieval_output", "{}")
    reasoning_output = state.get("reasoning_output", "{}")

    log_chunk = ""
    user_content = getattr(tool_context, "user_content", None)
    if user_content is not None and getattr(user_content, "parts", None):
        log_chunk = "\n".join(
            p.text for p in user_content.parts if getattr(p, "text", None)
        )

    return await run_ensemble(log_chunk, retrieval_output, reasoning_output)
