"""Pydantic-settings wrapper for the agent system.

All env vars come from `rca-agent-system/.env` (gitignored). The Settings
class is the single source of truth -- every other module reads through
`settings`, never `os.getenv` directly. This keeps the env-var surface
small and discoverable.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        # Don't blow up if the user has unrelated env vars in their shell.
        extra="ignore",
        # Env-var names are case-insensitive on the OS side anyway, but
        # being explicit avoids platform surprises.
        case_sensitive=False,
    )

    # --- Gemini auth ---
    # The free-tier Gemini API key from https://aistudio.google.com/apikey.
    google_api_key: str = ""

    # When "FALSE", ADK uses the public Gemini API (API-key auth).
    # When "TRUE", ADK uses Vertex AI (requires gcloud auth).
    google_genai_use_vertexai: str = "FALSE"

    # --- ADK server ---
    adk_port: int = 8000
    adk_cors_origins: str = "http://localhost:3000"

    # --- Storage ---
    # Vector store (Phase 6+).
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "incident_memory"

    # Session DB. Must use the async driver -- ADK's DatabaseSessionService
    # checks for sqlite+aiosqlite:// (not plain sqlite://).
    session_db_url: str = "sqlite+aiosqlite:///./data/sessions.db"

    # --- Model ---
    gemini_model: str = "gemini-2.5-flash"

    @property
    def cors_origins_list(self) -> list[str]:
        """Comma-separated origins -> list, trimmed and de-empty'd."""
        return [
            o.strip()
            for o in self.adk_cors_origins.split(",")
            if o.strip()
        ]


settings = Settings()
