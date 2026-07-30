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
    except Exception as exc:  # noqa: BLE001 - map any inference failure to a 500
        # The exception text can carry model paths / tensor internals, so it
        # stays in the server log and the client gets a generic message.
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail="inference error") from exc

    return ClassifyResponse(**result)
