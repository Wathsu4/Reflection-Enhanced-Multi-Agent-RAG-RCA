"""ADK function tool: retrieve similar past incidents from memory.

Gemini reads this function's docstring to decide *when* to call it and
how to fill the arguments. So the docstring is part of the public API
of the tool -- edit it carefully.

The tool also implements the first piece of "dynamic memory": hits are
re-ranked by `similarity * success_score`. Until reflection (Phase 7)
starts adjusting scores, this is identical to similarity ranking; once
reflection runs, frequently-helpful incidents float up and discredited
ones sink.
"""

from __future__ import annotations

from typing import Any

from rca_system.memory.chroma_store import IncidentMemory

# Module-level singleton: opening a Chroma client is cheap on subsequent
# calls (it shares the on-disk index) but the *first* construction
# pulls the embedding model. Keeping one instance avoids redundant
# warmups across tool invocations within a process.
_memory: IncidentMemory | None = None


def _get_memory() -> IncidentMemory:
    """Lazy-init so test harnesses can monkey-patch `_memory` before
    any tool call without paying for a real ChromaDB warmup."""
    global _memory
    if _memory is None:
        _memory = IncidentMemory()
    return _memory


def retrieve_incidents(query: str, k: int = 5) -> dict[str, Any]:
    """Retrieve up to `k` past incident records most similar to the given query.

    Args:
        query: Natural-language description of the current incident, or relevant
            log excerpts. The more specific (error messages, component names,
            symptom keywords), the better the matches.
        k: Number of results to return (1-10). Defaults to 5.

    Returns:
        A dict with a single key `hits`, where each element contains:
          - incident_id (str)
          - title (str)
          - severity (str)
          - root_cause (str)
          - resolution (str)
          - similarity (float, 0.0-1.0; cosine similarity to the query)
          - success_score (float, 0.0-2.0; 1.0 is neutral, higher means
            this entry has historically led to correct diagnoses)
        Hits are sorted by `similarity * success_score` (descending), so
        the most useful prior incident appears first.
    """
    # Defensively clamp -- Gemini sometimes passes nonsense values like
    # k=0 or k=100 when it misreads the docstring.
    k = max(1, min(10, int(k)))

    memory = _get_memory()
    raw = memory.query(query, k=k)

    # Side effect: bump usage counters. Done *before* re-ranking so the
    # popularity stats reflect what was actually retrieved (similarity-
    # based), not what was returned to the agent.
    memory.mark_retrieved([h["incident_id"] for h in raw])

    hits: list[dict[str, Any]] = []
    for h in raw:
        m = h["metadata"]
        hits.append(
            {
                "incident_id": h["incident_id"],
                "title": m.get("title", ""),
                "severity": m.get("severity", ""),
                "root_cause": m.get("root_cause", ""),
                "resolution": m.get("resolution", ""),
                "similarity": round(h["similarity"], 4),
                "success_score": round(
                    float(m.get("success_score", 1.0)), 3
                ),
            }
        )

    # Dynamic re-ranking: weight similarity by per-incident success score.
    # Until reflection runs, success_score == 1.0 for every record so
    # this is a no-op; afterwards it lets the system "learn" which
    # historical incidents are actually informative.
    hits.sort(
        key=lambda x: x["similarity"] * x["success_score"], reverse=True
    )
    return {"hits": hits}
