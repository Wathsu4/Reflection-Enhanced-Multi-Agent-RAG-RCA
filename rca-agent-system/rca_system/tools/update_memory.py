"""ADK function tool: apply reflection-driven score deltas to memory.

This is the only place in the system where a non-seed write happens to
the success_score field of incident records. Keeping the surface area
small makes the dynamic-memory behaviour auditable.
"""

from __future__ import annotations

from typing import Any

from rca_system.memory.chroma_store import IncidentMemory

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
            (number). The reflection tool already clamps deltas to
            [-0.2, +0.2]; this function clamps the resulting score to
            [0.0, 2.0] so a successful incident never accumulates an
            unbounded reputation.

    Returns:
        A dict with key `updated`, mapping each *processed* incident_id
        to a record like
            {"old_score": 1.0, "new_score": 1.1, "delta": 0.1}.
        Incidents that don't exist in memory are silently skipped (the
        reflection agent may name an id from a prior run that has since
        been removed).
    """
    memory = _get_memory()
    collection = memory._collection  # noqa: SLF001 -- intentional internal access

    if not isinstance(incident_score_deltas, dict):
        return {"updated": {}}

    results: dict[str, dict[str, float]] = {}
    for incident_id, raw_delta in incident_score_deltas.items():
        try:
            delta = float(raw_delta)
        except (TypeError, ValueError):
            continue

        before = collection.get(ids=[str(incident_id)], include=["metadatas"])
        if not before["ids"]:
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

    return {"updated": results}
