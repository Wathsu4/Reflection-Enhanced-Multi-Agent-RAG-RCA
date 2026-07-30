"""ADK function tool: apply reflection-driven score deltas to memory.

This is the only place in the system where a non-seed write happens to
the success_score field of incident records. Keeping the surface area
small makes the dynamic-memory behaviour auditable.
"""

from __future__ import annotations

import logging
from typing import Any

from rca_system.memory.chroma_store import IncidentMemory

logger = logging.getLogger(__name__)

# Module-level singleton: same lazy-init pattern as `retrieve_incidents`.
# The first call constructs an `IncidentMemory`, which warms the
# embedding model. Tests monkeypatch this directly.
_memory: IncidentMemory | None = None


def _get_memory() -> IncidentMemory:
    global _memory
    if _memory is None:
        _memory = IncidentMemory()
    return _memory


def apply_reflection_to_memory(
    incident_score_deltas: dict[str, float],
) -> dict[str, Any]:
    """Apply the reflection agent's score deltas to stored incidents.

    Args:
        incident_score_deltas: Map of incident_id (string) to score delta
            (number). By the time a delta reaches here it has already
            been clamped to [-0.2, +0.2] and deterministically gated
            (Tier 0 Phase 1: dropped if not genuinely used / zero /
            over the per-call negative cap -- see
            `rca_system/tools/record_reflection.py`). This function
            hands the delta to `IncidentMemory.update_score`, which
            converts it to a pseudo-count and folds it into the
            incident's alpha/beta prior (Tier 0 Phase 2); the resulting
            `success_score = 2*alpha/(alpha+beta)` is bounded to
            (0.0, 2.0) by construction, not by an explicit clamp, and
            asymptotically resists any single run dominating it.

    Returns:
        A dict with keys `updated` -- mapping each *processed*
        incident_id to a record like
            {"old_score": 1.0, "new_score": 1.1, "delta": 0.1}
        -- and `skipped`, mapping each incident_id that was NOT applied
        to the reason ("unknown_incident" / "invalid_delta"). Skipping is
        expected (the reflection agent may name an id from a prior run
        that has since been removed) but is reported rather than
        swallowed, so a run where nothing was written is
        distinguishable from one where nothing was proposed.
    """
    memory = _get_memory()
    collection = memory._collection  # noqa: SLF001 -- intentional internal access

    if not isinstance(incident_score_deltas, dict):
        logger.warning(
            "Ignoring incident_score_deltas of unsupported type %s; no memory writes",
            type(incident_score_deltas).__name__,
        )
        return {"updated": {}, "skipped": {}}

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

        before = collection.get(ids=[str(incident_id)], include=["metadatas"])
        if not before["ids"]:
            logger.warning("Skipping incident %r: not present in memory", incident_id)
            skipped[str(incident_id)] = "unknown_incident"
            continue
        old = float((before["metadatas"][0] or {}).get("success_score", 1.0))

        memory.update_score(str(incident_id), delta)

        after = collection.get(ids=[str(incident_id)], include=["metadatas"])
        new = float((after["metadatas"][0] or {}).get("success_score", 1.0))

        results[str(incident_id)] = {
            "old_score": round(old, 3),
            "new_score": round(new, 3),
            "delta": round(delta, 3),
        }

    return {"updated": results, "skipped": skipped}
