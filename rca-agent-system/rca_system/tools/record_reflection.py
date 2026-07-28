"""ADK function tool: persist the reflection agent's verdict.

This tool is a *structuring* step, not a memory mutation. It clamps and
shape-checks the reflection agent's score deltas so the downstream
memory-update agent can apply them safely. Memory is not modified
here -- that happens in `apply_reflection_to_memory`.

Splitting the steps gives us clean separation:
  reflection_agent -> structures + clamps  (this tool)
  memory_update_agent -> applies to ChromaDB

Tier 0 Phase 1 (How-To-Improve/TIER0_PLAN.md SS4) adds deterministic delta
gating. Gemini cannot be trusted to reliably follow a prompt-only rule
like "omit the key if neutral" -- in practice it defaults to small
negative nudges far more often than to omission, which produces a
systematic Matthew-effect bias against frequently-retrieved incidents.
So the gate is enforced here, in code, instead of hoped for in the
instruction.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from rca_system.settings import settings

# Per-incident delta is bounded so a single bad reflection cycle can't
# wreck the score for an incident. After ~5 bad runs, score still drops
# only by 1.0 -- recoverable.
_DELTA_MIN = -0.2
_DELTA_MAX = 0.2

OverallQuality = Literal["high", "medium", "low"]
_VALID_QUALITIES = {"high", "medium", "low"}


def _normalize_id_list(value: Any) -> list[str] | None:
    """Coerce a tool argument into a list of string ids, or `None`.

    `None` is the caller's explicit "not provided" signal, which disables
    the corresponding gate/cap (see `record_reflection`'s docstring). Any
    other malformed shape degrades to `None` rather than raising -- this
    tool must never blow up the pipeline on odd Gemini output.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return None


def _gate_deltas(
    clamped: dict[str, float],
    used_ids: list[str] | None,
    retrieved_ids: list[str] | None,
) -> tuple[dict[str, float], int, int]:
    """Apply Tier 0 Phase 1's deterministic delta gate.

    Rules (TIER0_PLAN.md SS4):
      * A delta of exactly 0.0 is always dropped -- a no-op delta carries
        no information and should never reach `apply_reflection_to_memory`.
      * If `retrieved_ids` is known, any id outside it is dropped entirely
        (whichever sign) -- it can't be verified against either gate below
        (e.g. a hallucinated id that was never actually retrieved).
      * A positive delta survives only if its id is in `used_ids` (when
        known); otherwise it's dropped, not zeroed -- "genuinely relevant"
        is judged by actual use, not by the reflection agent's say-so.
      * Negative deltas are capped in *count*, not silently trusted: at
        most `ceil(len(retrieved_ids) * settings.max_negative_delta_fraction)`
        survive (when `retrieved_ids` is known); the largest-magnitude
        negatives are kept and the rest dropped.
      * `used_ids is None` / `retrieved_ids is None` disables the
        corresponding gate ("gate nothing" / "cap nothing" respectively)
        -- this is the back-compat contract for callers that predate
        Phase 1 (direct unit tests, e.g.).

    Returns `(gated_deltas, positive_dropped_count, negative_dropped_count)`.
    """
    used_set = set(used_ids) if used_ids is not None else None
    retrieved_set = set(retrieved_ids) if retrieved_ids is not None else None

    gated: dict[str, float] = {}
    positive_dropped = 0
    negative_dropped = 0
    negative_candidates: list[tuple[str, float]] = []

    for incident_id, delta in clamped.items():
        if delta == 0.0:
            continue

        if retrieved_set is not None and incident_id not in retrieved_set:
            if delta > 0:
                positive_dropped += 1
            else:
                negative_dropped += 1
            continue

        if delta > 0:
            if used_set is not None and incident_id not in used_set:
                positive_dropped += 1
                continue
            gated[incident_id] = delta
        else:
            negative_candidates.append((incident_id, delta))

    if retrieved_set is not None:
        cap = math.ceil(len(retrieved_set) * settings.max_negative_delta_fraction)
    else:
        cap = len(negative_candidates)  # "cap nothing"

    # Most-negative (largest magnitude) first; stable sort preserves the
    # original proposal order as the tie-break.
    negative_candidates.sort(key=lambda kv: kv[1])
    kept, overflow = negative_candidates[:cap], negative_candidates[cap:]
    negative_dropped += len(overflow)
    for incident_id, delta in kept:
        gated[incident_id] = delta

    return gated, positive_dropped, negative_dropped


def record_reflection(
    incident_score_deltas: dict[str, float],
    overall_quality: str,
    rationale: str,
    used_incident_ids: list[str] | None = None,
    retrieved_incident_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Persist the reflection agent's judgment about the current RCA run.

    Args:
        incident_score_deltas: Map of incident_id (string) to score delta
            (number). Positive deltas (up to +0.2) mean the incident was
            genuinely helpful in diagnosing the current case; negative
            deltas (down to -0.2) mean it was misleading or irrelevant.
            Values outside [-0.2, +0.2] will be clamped, not rejected.
        overall_quality: One of "high", "medium", "low" -- your verdict
            on the reasoning agent's hypothesis.
        rationale: Short paragraph (1-3 sentences) explaining the verdict.
            Name any incident you assign a negative delta to.
        used_incident_ids: The incident_ids the reasoning agent actually
            cited as evidence (its `used_incident_ids` field). A positive
            delta for any id NOT in this list is dropped, not zeroed --
            pass every id the reasoning agent used, even ones you disagree
            with (disagreement is a negative delta, not an omission).
        retrieved_incident_ids: The incident_ids that were actually
            retrieved this run (from the retrieval JSON's hits). A delta
            for any id outside this list is dropped -- it can't be
            verified against anything. Also bounds how many negative
            deltas can be applied in one call, so one skeptical reflection
            pass can't drain the whole retrieved set.

    Returns:
        A dict with the structured reflection record. Memory is NOT
        modified here; the memory-update agent will read this and apply
        the (gated) deltas in a separate step. Includes a `_debug` key
        reporting how many proposed deltas the gate dropped, by sign --
        evaluation-only; the production pipeline ignores it.
    """
    if not isinstance(incident_score_deltas, dict):
        # Defensive: Gemini sometimes hands us a list of {id, delta}
        # objects instead of a flat mapping. Normalise on the spot
        # rather than failing the whole pipeline.
        if isinstance(incident_score_deltas, list):
            incident_score_deltas = {
                str(item.get("incident_id") or item.get("id")): float(
                    item.get("delta") or item.get("score") or 0.0
                )
                for item in incident_score_deltas
                if isinstance(item, dict)
            }
        else:
            incident_score_deltas = {}

    clamped: dict[str, float] = {}
    for incident_id, raw in incident_score_deltas.items():
        try:
            delta = float(raw)
        except (TypeError, ValueError):
            continue
        clamped[str(incident_id)] = max(_DELTA_MIN, min(_DELTA_MAX, delta))

    quality = overall_quality.strip().lower() if isinstance(overall_quality, str) else ""
    if quality not in _VALID_QUALITIES:
        # Don't silently drop a misformatted verdict; tag it as unknown
        # so reviewers can spot misbehaving reflection runs in logs.
        quality = "unknown"

    gated, positive_dropped, negative_dropped = _gate_deltas(
        clamped,
        _normalize_id_list(used_incident_ids),
        _normalize_id_list(retrieved_incident_ids),
    )

    return {
        "status": "recorded",
        "incident_score_deltas": gated,
        "overall_quality": quality,
        "rationale": str(rationale or "").strip(),
        "_debug": {
            "positive_dropped_count": positive_dropped,
            "negative_dropped_count": negative_dropped,
        },
    }
