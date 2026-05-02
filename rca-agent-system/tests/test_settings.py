"""Settings-loading tests.

We deliberately use `Settings()` with explicit kwargs (rather than
relying on a real `.env` file) so the tests are deterministic and don't
leak whatever the local dev has in their environment.
"""

from __future__ import annotations

from rca_system.settings import Settings


def test_defaults_match_phase_5_spec() -> None:
    """If someone changes a default that downstream code relies on, this
    test catches it before deployment."""
    s = Settings(google_api_key="dummy")
    assert s.adk_port == 8000
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.google_genai_use_vertexai == "FALSE"
    # Must use the *async* SQLAlchemy driver -- ADK's session service
    # rejects plain `sqlite://`.
    assert "aiosqlite" in s.session_db_url


def test_cors_origins_list_splits_and_trims() -> None:
    s = Settings(
        google_api_key="dummy",
        adk_cors_origins="http://localhost:3000, https://demo.example.com ,",
    )
    assert s.cors_origins_list == [
        "http://localhost:3000",
        "https://demo.example.com",
    ]


def test_cors_origins_list_handles_empty_string() -> None:
    s = Settings(google_api_key="dummy", adk_cors_origins="")
    assert s.cors_origins_list == []
