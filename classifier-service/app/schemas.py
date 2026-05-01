"""Request/response models. These are the wire contract between the
classifier service and the Next.js frontend (see §7 of the implementation
guide). Any change here MUST be mirrored in `frontend/src/lib/types.ts`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import settings

Severity = Literal["FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"]
Priority = Literal["critical", "high", "low", "none"]
Profile = Literal["normal", "warning", "error", "fatal", "mixed"]


# ---------- /classify ----------


class ClassifyRequest(BaseModel):
    log_chunk: str = Field(..., description="Newline-joined log lines to classify.")

    @field_validator("log_chunk")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("log_chunk must not be empty")
        return v

    @field_validator("log_chunk")
    @classmethod
    def _within_size_limit(cls, v: str) -> str:
        # Encoded byte length, not Python string length, to be honest about
        # what's being shipped.
        if len(v.encode("utf-8")) > settings.max_chunk_bytes:
            raise ValueError(
                f"log_chunk exceeds max size of {settings.max_chunk_bytes} bytes"
            )
        return v


class ClassifyResponse(BaseModel):
    severity: Severity
    severity_id: int
    confidence: float
    should_invoke_rca: bool
    priority: Priority
    inference_ms: float
    all_probabilities: dict[Severity, float]


# ---------- /generate-logs ----------


class GenerateLogsRequest(BaseModel):
    profile: Profile = "mixed"
    num_lines: int = Field(30, ge=1, le=200)
    seed: int | None = None


class GenerateLogsResponse(BaseModel):
    log_chunk: str
    intended_severity: Severity
    num_lines: int


# ---------- /health ----------


class HealthResponse(BaseModel):
    status: Literal["ok", "starting", "error"]
    model_loaded: bool
    device: str
