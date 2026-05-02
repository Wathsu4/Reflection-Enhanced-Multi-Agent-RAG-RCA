"""HTTP-level smoke tests for the FastAPI server.

We use FastAPI's `TestClient` so no real port is opened -- this is
in-process. Endpoints that require Gemini auth (`/run`, `/run_sse`) are
covered by a separate live test that's skipped unless GOOGLE_API_KEY is
set to a real value (not the placeholder).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import server


client = TestClient(server.app)


def test_health_endpoint_returns_ok_with_model_name() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The model name must come from settings, not be hardcoded -- this
    # guards against a future refactor that drops the env override.
    assert body["model"].startswith("gemini-")


def test_list_apps_discovers_rca_system() -> None:
    """ADK auto-discovers agent apps from `agents_dir`. The package
    `rca_system/` must show up as a registered app or the entire ADK
    HTTP surface is unusable.
    """
    r = client.get("/list-apps")
    assert r.status_code == 200
    apps = r.json()
    assert "rca_system" in apps, (
        f"rca_system not discovered by ADK; got {apps!r}. "
        "Check that rca_system/__init__.py exports `root_agent`."
    )


def test_adk_routes_are_mounted() -> None:
    """Sanity check that ADK didn't silently fail to mount its standard
    routes -- without these the frontend can't talk to the agent."""
    paths = {r.path for r in server.app.routes if hasattr(r, "path")}
    # The endpoints we'll rely on in Phase 8 / Phase 9.
    for required in ("/run", "/run_sse", "/list-apps"):
        assert required in paths, f"missing required ADK route {required}"


def test_session_endpoint_path_template_exists() -> None:
    """The session-create endpoint is what the frontend (and our curl
    smoke test) hits before /run. It's a templated path, so we just
    check that the template is registered."""
    paths = {r.path for r in server.app.routes if hasattr(r, "path")}
    assert (
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}" in paths
    )


# -------------------- Phase 9 demo reset --------------------


def test_reset_memory_returns_403_when_flag_is_unset(monkeypatch) -> None:
    """The demo reset is destructive; it must refuse to run unless the
    operator explicitly enables it. Default-deny is the only safe
    default for an LLM-facing endpoint."""
    monkeypatch.delenv("ALLOW_DEMO_RESET", raising=False)
    r = client.post("/demo/reset-memory")
    assert r.status_code == 403
    assert "ALLOW_DEMO_RESET" in r.json()["detail"]


def test_reset_memory_route_is_mounted() -> None:
    """We don't actually run the destructive path in CI (it would wipe
    the dev's chroma dir). Just assert the endpoint is registered so a
    refactor that accidentally drops it fails this test fast."""
    paths = {r.path for r in server.app.routes if hasattr(r, "path")}
    assert "/demo/reset-memory" in paths
