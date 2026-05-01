"""GET /health — liveness + model-load + device info."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    classifier = getattr(request.app.state, "classifier", None)
    if classifier is None:
        return HealthResponse(status="starting", model_loaded=False, device="unknown")
    return HealthResponse(
        status="ok",
        model_loaded=True,
        device=classifier.device,
    )
