"""Tests for the evaluation console API.

Three layers:
  * registry  -- pure metadata + param-arg construction (no I/O).
  * routes    -- HTTP surface via FastAPI TestClient (read-only + error
    paths; no real subprocess spawning).
  * jobs      -- the JobManager lifecycle end-to-end with a *faked*
    subprocess, so we exercise progress parsing / status transitions
    without calling Gemini or touching ChromaDB.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server
from rca_system.eval_api import jobs as jobs_mod
from rca_system.eval_api.jobs import EVAL_DIR, Job, JobBusyError, JobManager
from rca_system.eval_api.registry import (
    get_experiment,
    list_experiments,
)

client = TestClient(server.app)


# -------------------- registry --------------------


def test_registry_has_runnable_and_planned() -> None:
    exps = list_experiments()
    assert len(exps) >= 10
    runnable = [e for e in exps if e.status == "runnable"]
    planned = [e for e in exps if e.status == "planned"]
    assert runnable and planned
    # Every runnable experiment must declare a script + outputs glob.
    for e in runnable:
        assert e.script in {
            "evaluate",
            "memory_evolution",
            "classifier_metrics",
            "ragas",
        }, e.id
        assert e.outputs_glob, e.id


def test_registry_ids_unique() -> None:
    ids = [e.id for e in list_experiments()]
    assert len(ids) == len(set(ids))


def test_build_command_args_defaults_and_overrides() -> None:
    mem = get_experiment("memory-evolution")
    assert mem is not None
    assert mem.build_command_args() == ["--ablation", "none", "--runs", "2", "--limit", "0"]
    assert mem.build_command_args({"runs": 4, "limit": 3}) == [
        "--ablation", "none", "--runs", "4", "--limit", "3",
    ]


def test_build_command_args_flag_param() -> None:
    full = get_experiment("pipeline-full")
    assert full is not None
    # store_true flag only appears when truthy.
    assert "--llm-judge" not in full.build_command_args({"llm_judge": False})
    assert "--llm-judge" in full.build_command_args({"llm_judge": True})


def test_build_command_args_validates_range() -> None:
    mem = get_experiment("memory-evolution")
    assert mem is not None
    with pytest.raises(ValueError):
        mem.build_command_args({"runs": 99})


# -------------------- routes (read-only + error paths) --------------------


def test_list_experiments_endpoint() -> None:
    r = client.get("/eval/experiments")
    assert r.status_code == 200
    body = r.json()
    assert "experiments" in body and isinstance(body["experiments"], list)
    assert "busy" in body
    ids = {e["id"] for e in body["experiments"]}
    assert "pipeline-full" in ids


def test_experiment_detail_endpoint_and_404() -> None:
    r = client.get("/eval/experiments/pipeline-full")
    assert r.status_code == 200
    body = r.json()
    assert body["experiment"]["id"] == "pipeline-full"
    assert isinstance(body["results"], list)

    assert client.get("/eval/experiments/does-not-exist").status_code == 404


def test_run_unknown_experiment_404() -> None:
    assert client.post("/eval/experiments/nope/run", json={"params": {}}).status_code == 404


def test_run_planned_experiment_400() -> None:
    # A planned experiment is not runnable yet.
    r = client.post("/eval/experiments/pairwise-judge/run", json={"params": {}})
    assert r.status_code == 400


def test_run_bad_params_400() -> None:
    r = client.post(
        "/eval/experiments/pipeline-full/run", json={"params": {"limit": 999}}
    )
    assert r.status_code == 400


def test_run_returns_409_when_busy(monkeypatch) -> None:
    busy = Job(id="busy123", experiment_id="pipeline-full", title="x", status="running")
    monkeypatch.setitem(jobs_mod.job_manager._jobs, "busy123", busy)
    monkeypatch.setattr(jobs_mod.job_manager, "_current_id", "busy123")
    r = client.post("/eval/experiments/pipeline-full/run", json={"params": {}})
    assert r.status_code == 409


def test_jobs_and_job_404() -> None:
    assert client.get("/eval/jobs").status_code == 200
    assert client.get("/eval/jobs/unknown").status_code == 404
    assert client.post("/eval/jobs/unknown/cancel").status_code == 404


def test_result_path_traversal_guarded() -> None:
    # Escaping the eval/ tree must be rejected, not served.
    r = client.get("/eval/results/../../server.py")
    assert r.status_code in (400, 404)


# -------------------- job lifecycle (faked subprocess) --------------------


class _FakeProc:
    """Minimal stand-in for asyncio.subprocess.Process."""

    def __init__(self, lines: list[bytes], rc: int = 0) -> None:
        self._lines = lines
        self._rc = rc
        self.returncode: int | None = None
        self.stdout = self

    def __aiter__(self) -> "_FakeProc":
        self._it = iter(self._lines)
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._it)
        except StopIteration as exc:  # noqa: B904
            raise StopAsyncIteration from exc

    async def wait(self) -> int:
        self.returncode = self._rc
        return self._rc

    def terminate(self) -> None:
        self.returncode = -15


def _fake_run_done_event() -> bytes:
    md = EVAL_DIR / "experiments" / "results-no_rag-test.md"
    js = EVAL_DIR / "experiments" / "results-no_rag-test.json"
    return json.dumps(
        {
            "event": "run_done",
            "summary": {"n": 2, "keyword_accuracy_exact_or_partial": 0.5},
            "md_path": str(md),
            "json_path": str(js),
        }
    ).encode()


@pytest.fixture
def hermetic_manager(monkeypatch, tmp_path) -> JobManager:
    """A JobManager whose sandbox/jobs dirs are redirected to tmp and whose
    seeding is a no-op (so no ChromaDB / model download happens)."""
    monkeypatch.setattr(jobs_mod, "SANDBOX_ROOT", tmp_path / "eval-runs")
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", tmp_path / "jobs")
    jm = JobManager()

    async def _no_seed(env):  # noqa: ANN001, ANN202
        return None

    monkeypatch.setattr(jm, "_seed_sandbox", _no_seed)
    return jm


async def test_job_lifecycle_success(hermetic_manager, monkeypatch) -> None:
    lines = [
        json.dumps({"event": "run_start", "total": 2}).encode(),
        json.dumps({"event": "scenario_start", "i": 1, "n": 2, "id": "a"}).encode(),
        json.dumps({"event": "scenario_done", "i": 1, "n": 2, "id": "a"}).encode(),
        b"some human log line on stderr->stdout",
        json.dumps({"event": "scenario_done", "i": 2, "n": 2, "id": "b"}).encode(),
        _fake_run_done_event(),
    ]

    async def _fake_exec(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        return _FakeProc(lines, rc=0)

    monkeypatch.setattr(jobs_mod.asyncio, "create_subprocess_exec", _fake_exec)

    exp = get_experiment("ablation-no-rag")
    assert exp is not None
    job = await hermetic_manager.start(exp, {"limit": 2})
    assert hermetic_manager._task is not None
    await hermetic_manager._task

    assert job.status == "succeeded"
    assert job.progress.done == 2
    assert job.progress.total == 2
    assert job.summary == {"n": 2, "keyword_accuracy_exact_or_partial": 0.5}
    assert any("results-no_rag-test" in f for f in job.result_files)
    # Human log line landed in the tail.
    assert any("human log line" in line for line in job.log_tail)
    # Manager is free again afterwards.
    assert not hermetic_manager.is_busy()


async def test_job_lifecycle_failure_sets_failed(hermetic_manager, monkeypatch) -> None:
    async def _fake_exec(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        return _FakeProc([b"boom"], rc=1)

    monkeypatch.setattr(jobs_mod.asyncio, "create_subprocess_exec", _fake_exec)

    exp = get_experiment("ablation-no-rag")
    assert exp is not None
    job = await hermetic_manager.start(exp, {})
    await hermetic_manager._task
    assert job.status == "failed"
    assert job.returncode == 1


async def test_single_flight_rejects_second_start(hermetic_manager) -> None:
    # Manually mark the manager busy and assert start() refuses.
    running = Job(id="r1", experiment_id="ablation-no-rag", title="x", status="running")
    hermetic_manager._jobs["r1"] = running
    hermetic_manager._current_id = "r1"
    exp = get_experiment("ablation-no-rag")
    assert exp is not None
    with pytest.raises(JobBusyError):
        await hermetic_manager.start(exp, {})


async def test_start_rejects_planned_experiment(hermetic_manager) -> None:
    exp = get_experiment("pairwise-judge")
    assert exp is not None and exp.status == "planned"
    with pytest.raises(RuntimeError):
        await hermetic_manager.start(exp, {})
