"""Wrapper around the fine-tuned ModernBERT log-severity classifier.

Loads the model once at construction time (slow on CPU, ~1s on GPU) and
exposes a single `classify(log_chunk)` method that returns a dict matching
`ClassifyResponse` in `schemas.py`.

The wrapper is safe for concurrent reads — HuggingFace forward passes are
re-entrant on a single model when wrapped in `torch.no_grad()`. We do not
batch requests here; FastAPI's per-request concurrency is sufficient for
demo workloads.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

logger = logging.getLogger(__name__)


_PRIORITY_MAP: dict[str, str] = {
    "FATAL_OR_CRITICAL": "critical",
    "ERROR": "high",
    "WARNING": "low",
    "NORMAL": "none",
}


def _resolve_device(requested: str) -> str:
    """Resolve `auto` / `cpu` / `cuda` / `mps` to a concrete device string."""
    requested = requested.lower()
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        # MPS = Apple Silicon. Faster than CPU but some ops fall back to CPU.
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA requested but not available; falling back to CPU.")
        return "cpu"
    if requested == "mps" and not (
        getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
    ):
        logger.warning("MPS requested but not available; falling back to CPU.")
        return "cpu"
    return requested


class LogSeverityClassifier:
    """Lightweight inference wrapper. Load once, call `classify` per request."""

    def __init__(self, model_path: Path, device: str = "auto") -> None:
        self.device = _resolve_device(device)

        meta_path = Path(model_path) / "training_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"training_metadata.json not found at {meta_path}. "
                "The model directory must be the output of the fine-tuning notebook."
            )
        with meta_path.open() as f:
            meta = json.load(f)

        # `id_to_label` keys come back as strings from JSON.
        self.id_to_label: dict[int, str] = {
            int(k): v for k, v in meta["id_to_label"].items()
        }
        self.max_length: int = int(meta.get("max_seq_length", 2048))

        logger.info("Loading tokenizer and model from %s ...", model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
        self.model.to(self.device).eval()
        logger.info("Model loaded on device=%s", self.device)

        # Warm up the kernel so the first real request isn't artificially slow.
        try:
            self.classify("warmup")
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning("Warmup pass failed (non-fatal): %s", exc)

    @torch.no_grad()
    def classify(self, log_chunk: str) -> dict:
        t0 = time.perf_counter()

        inputs = self.tokenizer(
            log_chunk,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self.device)
        logits = self.model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]
        pred_id = int(probs.argmax().item())
        confidence = float(probs[pred_id].item())
        severity = self.id_to_label[pred_id]

        return {
            "severity": severity,
            "severity_id": pred_id,
            "confidence": round(confidence, 4),
            "should_invoke_rca": severity in ("FATAL_OR_CRITICAL", "ERROR"),
            "priority": _PRIORITY_MAP[severity],
            "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
            "all_probabilities": {
                self.id_to_label[i]: round(float(probs[i].item()), 4)
                for i in range(len(probs))
            },
        }
