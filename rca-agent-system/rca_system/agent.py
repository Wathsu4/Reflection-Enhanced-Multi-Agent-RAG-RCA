"""Top-level `root_agent` for the RCA system.

Phase 6 (current): `root_agent` is the retrieval specialist directly,
so we can smoke-test the knowledge base end-to-end through the ADK HTTP
surface (`/run`, `adk web`).

Phase 7 will replace this with a `SequentialAgent` that wires retrieval
+ reasoning + reflection + memory-update into a single pipeline. The
re-export contract (the symbol `root_agent`) stays the same -- only its
construction changes.

ADK discovers this agent by importing the `rca_system` package and
looking for the symbol `root_agent` (re-exported from `__init__.py`).
"""

from __future__ import annotations

from rca_system.agents.retrieval_agent import retrieval_agent

# Temporary: expose the retrieval agent directly. The downstream phases
# will swap this for a real orchestrator without changing the import
# site (server.py, tests).
root_agent = retrieval_agent
