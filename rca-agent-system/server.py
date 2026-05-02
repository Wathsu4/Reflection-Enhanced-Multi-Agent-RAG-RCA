"""Production entrypoint for the RCA agent system.

We use ADK's `get_fast_api_app()` helper, which:
  * Discovers agent apps under `agents_dir` (each subdirectory whose
    `__init__.py` exports `root_agent` becomes one).
  * Wires up the standard ADK endpoints: /list-apps, /run, /run_sse,
    session management, etc.
  * Persists sessions to the configured SQL DB.

We then attach our own `/health` endpoint so the rest of the system has
the same readiness contract as `classifier-service`.

Run with:
    uv run python server.py
or for the ADK web UI (debugging):
    uv run adk web
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from google.adk.cli.fast_api import get_fast_api_app

from rca_system.settings import settings


def _is_real_agent_app(name: str) -> bool:
    """Return True if `name` is a Python package that actually exports a
    `root_agent`.

    ADK 1.32's auto-discovery treats every immediate subdirectory of
    `agents_dir` as a candidate app, even ones that aren't agent packages
    (e.g. `data/`, `tests/`). We use this helper to filter the
    `/list-apps` response so the frontend only sees usable agents.
    """
    try:
        mod = importlib.import_module(name)
    except Exception:
        return False
    return hasattr(mod, "root_agent")

# `agents_dir` is the *parent* of the agent-app package. ADK walks this
# directory and treats each immediate subdirectory whose package exports
# `root_agent` as a separate app. Pointing it at the project root means
# `rca_system/` is discovered as the app name "rca_system".
AGENTS_DIR = str(Path(__file__).parent.resolve())

app: FastAPI = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    session_service_uri=settings.session_db_url,
    allow_origins=settings.cors_origins_list,
    # Set to True to also mount ADK's built-in debug web UI under "/".
    # We keep it False here because our own Next.js frontend is the
    # primary surface; flip this on transiently when debugging.
    web=False,
)


# ADK 1.32 auto-registers its own minimal `/health` returning just
# `{"status":"ok"}` and a `/list-apps` that includes every sibling
# directory of the agents_dir (data/, tests/, etc.). FastAPI dispatches
# to the first matching route, so without filtering, our richer
# implementations would be shadowed. Strip ADK's defaults so ours win.
app.router.routes = [
    r for r in app.router.routes
    if getattr(r, "path", None) not in {"/health", "/list-apps"}
]


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Readiness probe.

    Doesn't actually call Gemini -- just confirms the app loaded and
    surfaces the model name so a frontend can display "RCA service: OK
    (gemini-2.5-flash)".
    """
    return {"status": "ok", "model": settings.gemini_model}


@app.get("/list-apps", tags=["meta"])
async def list_apps() -> list[str]:
    """Return only directories that are real agent packages (i.e.
    expose `root_agent`). ADK's default lists every subdirectory of
    `agents_dir`, which surfaces noise like `data/` and `tests/`."""
    candidates = [
        p.name for p in Path(AGENTS_DIR).iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    ]
    return sorted(c for c in candidates if _is_real_agent_app(c))


@app.post("/demo/reset-memory", tags=["demo"])
async def reset_memory() -> dict[str, object]:
    """Wipe and re-seed ChromaDB. Phase 9 demo helper.

    GUARD: only enabled when `ALLOW_DEMO_RESET=1` is set in the env --
    resetting the dynamic memory between unrelated production runs
    would erase the reflection-driven score adjustments we want to
    measure, so this is deliberately not a default-on endpoint.

    The implementation imports `scripts.reset_memory.reset_memory` and
    calls it directly rather than spawning a subprocess: it's already
    correct (clears chromadb's process-wide cache before rmtree, then
    reseeds), and avoiding `subprocess` keeps the runtime serverless-
    friendly.
    """
    if os.getenv("ALLOW_DEMO_RESET") != "1":
        raise HTTPException(
            status_code=403,
            detail=(
                "Demo reset is disabled. Set ALLOW_DEMO_RESET=1 in the "
                "agent service environment to enable this endpoint."
            ),
        )
    # Local import: keeps server cold-start fast when the endpoint
    # isn't exercised, and avoids loading the chromadb client until
    # the user actually asks for a reset.
    from scripts.reset_memory import reset_memory as _reset
    from rca_system.memory.chroma_store import IncidentMemory

    rc = _reset()
    if rc != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Reset/reseed exited with code {rc}",
        )
    return {"status": "ok", "count": IncidentMemory().count()}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.adk_port,
    )
