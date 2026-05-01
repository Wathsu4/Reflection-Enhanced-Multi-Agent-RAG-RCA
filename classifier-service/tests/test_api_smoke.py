"""HTTP-level smoke tests that DO require the trained model.

These are skipped automatically if the model directory is missing, so the
test suite remains green on a machine that hasn't downloaded the model yet.

Run only the model-dependent tests with:
    pytest tests/test_api_smoke.py
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings


pytestmark = pytest.mark.skipif(
    not (settings.model_path / "training_metadata.json").exists()
    or os.environ.get("CLASSIFIER_SKIP_MODEL_TESTS") == "1",
    reason=(
        "Trained model not found at configured CLASSIFIER_MODEL_PATH. "
        "These tests require the fine-tuned ModernBERT model directory."
    ),
)


@pytest.fixture(scope="module")
def client():
    # Import inside the fixture so the model only loads when these tests run.
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["device"] in {"cpu", "cuda", "mps"}


def test_classify_error_chunk(client):
    chunk = "2024-01-15 ERROR Connection refused to Redis\n" * 5
    r = client.post("/classify", json={"log_chunk": chunk})
    assert r.status_code == 200
    body = r.json()
    assert body["severity"] in ("ERROR", "FATAL_OR_CRITICAL")
    assert body["should_invoke_rca"] is True
    assert 0.0 <= body["confidence"] <= 1.0
    assert sum(body["all_probabilities"].values()) == pytest.approx(1.0, abs=0.01)


def test_classify_empty_returns_422(client):
    # Pydantic validators raise 422 by default for invalid bodies.
    r = client.post("/classify", json={"log_chunk": ""})
    assert r.status_code == 422


def test_generate_logs_fatal_profile(client):
    r = client.post(
        "/generate-logs",
        json={"profile": "fatal", "num_lines": 30, "seed": 7},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intended_severity"] == "FATAL_OR_CRITICAL"
    assert body["num_lines"] == 30
    assert body["log_chunk"].count("\n") == 29
