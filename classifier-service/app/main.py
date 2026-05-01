"""FastAPI entry point for the classifier service.

Run with:
    uv run uvicorn app.main:app --port 8001 --reload
or:
    python -m uvicorn app.main:app --port 8001 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .classifier import LogSeverityClassifier
from .config import settings
from .routers import classify, generate, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("classifier-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model on startup; release on shutdown.

    Loading happens here (not at module import) so failures surface as
    proper FastAPI startup errors and `/health` can report `starting` while
    a slower load is in progress.
    """
    logger.info(
        "Starting classifier-service. model_path=%s device=%s",
        settings.model_path,
        settings.device,
    )
    try:
        app.state.classifier = LogSeverityClassifier(
            model_path=settings.model_path,
            device=settings.device,
        )
    except FileNotFoundError as exc:
        # Helpful message when the model directory hasn't been downloaded yet.
        logger.error(
            "Failed to load model: %s\n"
            "Place the fine-tuned model at %s before starting the service.",
            exc,
            settings.model_path,
        )
        # Re-raise so uvicorn exits with non-zero — silent failure is worse.
        raise

    yield
    # No teardown necessary; PyTorch releases on process exit.
    logger.info("classifier-service shutting down")


app = FastAPI(
    title="Log Severity Classifier",
    description="Fine-tuned ModernBERT model behind a small HTTP wrapper.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS must be registered before routers so preflight `OPTIONS` requests
# are handled correctly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(classify.router)
app.include_router(generate.router)
