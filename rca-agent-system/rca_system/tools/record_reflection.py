"""ADK function tool: persist the reflection agent's verdict.

This tool is a *structuring* step, not a memory mutation. It clamps and
shape-checks the reflection agent's score deltas so the downstream
memory-update agent can apply them safely. Memory is not modified
here -- that happens in `apply_reflection_to_memory`.

Splitting the steps gives us clean separation:
  reflection_agent -> structures + clamps  (this tool)
  memory_update_agent -> applies to ChromaDB
"""

from __future__ import annotations

from typing import Any, Literal

# Per-incident delta is bounded so a single bad reflection cycle can't
# wreck the score for an incident. After ~5 bad runs, score still drops
# only by 1.0 -- recoverable.
_DELTA_MIN = -0.2
_DELTA_MAX = 0.2

OverallQuality = Literal["high", "medium", "low"]
_VALID_QUALITIES = {"high", "medium", "low"}


def record_reflection(
    incident_score_deltas: dict[str, float],
    overall_quality: str,
    rationale: str,
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

    Returns:
        A dict with the structured reflection record. Memory is NOT
        modified here; the memory-update agent will read this and apply
        the deltas in a separate step.
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

    return {
        "status": "recorded",
        "incident_score_deltas": clamped,
        "overall_quality": quality,
        "rationale": str(rationale or "").strip(),
    }
