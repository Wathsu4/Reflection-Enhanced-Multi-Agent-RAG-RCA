"""ADK function tool: retrieve similar past incidents from memory.

Gemini reads this function's docstring to decide *when* to call it and
how to fill the arguments. So the docstring is part of the public API
of the tool -- edit it carefully.

The tool also implements the first piece of "dynamic memory": hits are
re-ranked by `similarity * success_score`. Until reflection (Phase 7)
starts adjusting scores, this is identical to similarity ranking; once
reflection runs, frequently-helpful incidents float up and discredited
ones sink.

Tier 0 Phase 3 (How-To-Improve/TIER0_PLAN.md SS4/SS8) adds a small,
decaying exploration bonus on top of that product so a demoted incident
can't be *permanently* buried purely by the ranking formula -- it still
gets occasional chances to resurface and earn its way back up (or stay
down, if it keeps being unhelpful).
"""

from __future__ import annotations

import math
from typing import Any

from rca_system.memory.chroma_store import IncidentMemory
from rca_system.settings import settings

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


def _exploration_bonus(usage_count: int) -> float:
    """Tier 0 Phase 3 anti-starvation term.

    Equals `settings.exploration_bonus_weight` exactly at
    `usage_count == 0` and decays toward 0 as usage accumulates; never
    exceeds `exploration_bonus_weight` for any `usage_count >= 0`, so it
    can't overwhelm a genuinely strong match (`similarity * success_score`
    ranges up to 2.0).
    """
    return settings.exploration_bonus_weight * math.sqrt(1 / (1 + usage_count))


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
        Hits are sorted (descending) by `similarity * success_score` plus
        a small exploration bonus that decays as an incident accumulates
        retrievals, so the most useful prior incident usually appears
        first -- but a rarely-retrieved incident always gets some chance
        to resurface even if its success_score is currently low.
    """
    # Defensively clamp -- Gemini sometimes passes nonsense values like
    # k=0 or k=100 when it misreads the docstring.
    k = max(1, min(10, int(k)))

    memory = _get_memory()
    raw = memory.query(query, k=k)

    # Side effect: bump usage counters. Done *before* re-ranking so the
    # popularity stats reflect what was actually retrieved (similarity-
    # based), not what was returned to the agent. It also means the
    # exploration bonus below is computed from each incident's usage
    # count *prior to* this retrieval, not including it.
    memory.mark_retrieved([h["incident_id"] for h in raw])

    scored: list[tuple[dict[str, Any], float]] = []
    for h in raw:
        m = h["metadata"]
        similarity = round(h["similarity"], 4)
        success_score = round(float(m.get("success_score", 1.0)), 3)
        usage_count = int(m.get("usage_count", 0))

        hit = {
            "incident_id": h["incident_id"],
            "title": m.get("title", ""),
            "severity": m.get("severity", ""),
            "root_cause": m.get("root_cause", ""),
            "resolution": m.get("resolution", ""),
            "similarity": similarity,
            "success_score": success_score,
        }

        # Dynamic re-ranking: similarity weighted by per-incident success
        # score, PLUS a decaying exploration bonus (Tier 0 Phase 3) so a
        # demoted-but-rarely-retrieved incident can't be permanently
        # buried by the product term alone. Additive, not multiplicative
        # -- a success_score of exactly 0.0 still leaves the bonus term
        # intact. At usage_count=0 the bonus equals
        # exploration_bonus_weight (default 0.1); it shrinks toward 0 as
        # usage_count grows, and can never exceed exploration_bonus_weight
        # for any usage_count >= 0, so it can't overwhelm a genuinely
        # strong match (similarity * success_score ranges up to 2.0).
        rank_key = similarity * success_score + _exploration_bonus(usage_count)
        scored.append((hit, rank_key))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return {"hits": [hit for hit, _rank_key in scored]}
