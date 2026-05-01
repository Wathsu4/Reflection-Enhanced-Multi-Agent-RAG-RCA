"""POST /generate-logs — produce a synthetic log chunk for the simulator."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..log_generator import generate_log_chunk
from ..schemas import GenerateLogsRequest, GenerateLogsResponse

router = APIRouter(tags=["generate"])


@router.post("/generate-logs", response_model=GenerateLogsResponse)
async def generate_logs(body: GenerateLogsRequest) -> GenerateLogsResponse:
    try:
        chunk_text, intended_severity = generate_log_chunk(
            profile=body.profile,
            num_lines=body.num_lines,
            seed=body.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GenerateLogsResponse(
        log_chunk=chunk_text,
        intended_severity=intended_severity,  # type: ignore[arg-type]
        num_lines=body.num_lines,
    )
