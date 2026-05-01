"""Pydantic settings for the classifier service.

Values are read from (in order of precedence):
  1. Process environment variables prefixed with `CLASSIFIER_`
  2. Variables in `.env` (also prefixed)
  3. Defaults defined here.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLASSIFIER_",
        extra="ignore",
        case_sensitive=False,
    )

    model_path: Path = Path("./models/modernbert-log-severity-v1")
    device: str = "auto"  # auto | cpu | cuda | mps
    port: int = 8001
    cors_origins: str = "http://localhost:3000"  # comma-separated

    # Sanity guard: reject log chunks larger than this (bytes).
    max_chunk_bytes: int = 500_000

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
