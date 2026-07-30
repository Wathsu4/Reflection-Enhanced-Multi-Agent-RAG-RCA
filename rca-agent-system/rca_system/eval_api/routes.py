"""FastAPI routes for the evaluation console.

Mounted from `server.py` via `app.include_router(router)`. All paths are
under `/eval`. Runs are **not gated** but **single-flight** (a second
`run` while one is active returns 409). Reads (experiments, jobs, result
files) are always allowed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rca_system.eval_api.jobs import EVAL_DIR, Job, JobBusyError, job_manager
from rca_system.eval_api.registry import Experiment, get_experiment, list_experiments

router = APIRouter(prefix="/eval", tags=["eval"])


class RunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ResultEntry(BaseModel):
    """One past result file set for an experiment."""

    timestamp_ts: float
    size_bytes: int
    json_path: str | None = None  # relative to eval/
    markdown_path: str | None = None  # relative to eval/


class ExperimentListResponse(BaseModel):
    experiments: list[Experiment]
    busy: bool
    current_job_id: str | None = None


class ExperimentDetailResponse(BaseModel):
    experiment: Experiment
    results: list[ResultEntry]
    busy: bool
    current_job_id: str | None = None


class ResultFileResponse(BaseModel):
    path: str
    format: str  # "json" | "markdown"
    content: str


def _list_results(experiment: Experiment) -> list[ResultEntry]:
    """Find this experiment's past result files via its `outputs_glob`.

    Each primary match (a `.json` for pipeline runs, a `.md` for memory
    evolution) is paired with its sibling of the other extension if it
    exists. Sorted newest-first.
    """
    if not experiment.outputs_glob:
        return []
    matches = sorted(
        EVAL_DIR.glob(experiment.outputs_glob),
        key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
        reverse=True,
    )
    entries: list[ResultEntry] = []
    for m in matches:
        if not m.is_file():
            continue
        json_p = m if m.suffix == ".json" else m.with_suffix(".json")
        md_p = m if m.suffix == ".md" else m.with_suffix(".md")
        entries.append(
            ResultEntry(
                timestamp_ts=m.stat().st_mtime,
                size_bytes=m.stat().st_size,
                json_path=str(json_p.relative_to(EVAL_DIR)) if json_p.exists() else None,
                markdown_path=str(md_p.relative_to(EVAL_DIR)) if md_p.exists() else None,
            )
        )
    return entries


@router.get("/experiments", response_model=ExperimentListResponse)
async def get_experiments() -> ExperimentListResponse:
    cur = job_manager.current()
    return ExperimentListResponse(
        experiments=list_experiments(),
        busy=job_manager.is_busy(),
        current_job_id=cur.id if cur else None,
    )


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetailResponse)
async def get_experiment_detail(experiment_id: str) -> ExperimentDetailResponse:
    exp = get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"unknown experiment {experiment_id!r}")
    cur = job_manager.current()
    return ExperimentDetailResponse(
        experiment=exp,
        results=_list_results(exp),
        busy=job_manager.is_busy(),
        current_job_id=cur.id if cur else None,
    )


@router.post("/experiments/{experiment_id}/run", response_model=Job, status_code=202)
async def run_experiment(experiment_id: str, body: RunRequest | None = None) -> Job:
    exp = get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"unknown experiment {experiment_id!r}")
    if exp.status != "runnable" or exp.script is None:
        raise HTTPException(
            status_code=400,
            detail=f"experiment {experiment_id!r} is not runnable (status={exp.status})",
        )
    params = (body.params if body else None) or {}
    try:
        return await job_manager.start(exp, params)
    except JobBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"X-Running-Job": exc.running_job_id},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[Job])
async def get_jobs(limit: int = 20) -> list[Job]:
    return job_manager.recent(limit=max(1, min(100, limit)))


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, object]:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    cancelled = await job_manager.cancel(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


@router.get("/results/{file_path:path}", response_model=ResultFileResponse)
async def get_result(file_path: str) -> ResultFileResponse:
    """Return a result file's raw content. Guarded to the `eval/` tree."""
    eval_root = EVAL_DIR.resolve()
    target = (eval_root / file_path).resolve()
    # Path-traversal guard: the resolved path (symlinks included) must stay
    # strictly inside eval/. Absolute `file_path` values are also rejected
    # here, since `eval_root / "/etc/passwd"` resolves to `/etc/passwd`.
    if target == eval_root or not target.is_relative_to(eval_root):
        raise HTTPException(status_code=400, detail="invalid result path")
    if not target.is_file() or target.suffix not in {".json", ".md"}:
        raise HTTPException(status_code=404, detail="result file not found")
    fmt = "json" if target.suffix == ".json" else "markdown"
    return ResultFileResponse(
        path=str(target.relative_to(eval_root)),
        format=fmt,
        content=target.read_text(encoding="utf-8"),
    )


# Re-exported for tests / introspection.
__all__ = ["router", "_list_results"]


def _now() -> float:  # pragma: no cover - tiny helper kept for symmetry
    return time.time()


def _eval_dir() -> Path:  # pragma: no cover
    return EVAL_DIR
