"""POST /classify — run the trained classifier on a log chunk."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ..schemas import ClassifyRequest, ClassifyResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["classify"])


@router.post("/classify", response_model=ClassifyResponse)
async def classify(request: Request, body: ClassifyRequest) -> ClassifyResponse:
    classifier = getattr(request.app.state, "classifier", None)
    if classifier is None:
        # Lifespan startup hasn't finished, or the model failed to load.
        raise HTTPException(status_code=503, detail="classifier not ready")

    try:
        result = classifier.classify(body.log_chunk)
    except Exception as exc:  # noqa: BLE001 - we want to surface to the client
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=f"inference error: {exc}") from exc

    return ClassifyResponse(**result)
