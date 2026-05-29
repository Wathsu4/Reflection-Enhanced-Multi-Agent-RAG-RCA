"""Single-flight subprocess runner for evaluation experiments.

Why subprocess (not in-process):
  * Eval runs are long (Gemini-bound) and would otherwise block the live
    agent server's event loop.
  * They mutate `success_score`; running them in a **sandboxed** ChromaDB
    (a throwaway, freshly-seeded dir) keeps the live/demo memory untouched.
  * A child process exactly reproduces the CLI and is cleanly cancellable.

Concurrency: a single job runs at a time (`start` raises `JobBusyError`
if one is already running). Gemini rate limits + sandbox seeding make
concurrent runs unsafe, and the per-scenario cadence is slow enough that
the UI just polls `GET /eval/jobs/{id}`.

Progress: the child is launched with `--progress-json`, which makes it
emit one JSON line per lifecycle event on stdout. We tail that stream and
fold it into the `Job` model the polling endpoint returns.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from rca_system.eval_api.registry import Experiment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = PROJECT_ROOT / "eval"
EXPERIMENTS_DIR = EVAL_DIR / "experiments"
JOBS_DIR = EXPERIMENTS_DIR / ".jobs"
SANDBOX_ROOT = PROJECT_ROOT / "data" / "eval-runs"

_SCRIPT_PATHS: dict[str, Path] = {
    "evaluate": PROJECT_ROOT / "scripts" / "evaluate.py",
    "memory_evolution": PROJECT_ROOT / "scripts" / "evaluate_memory_evolution.py",
    "classifier_metrics": PROJECT_ROOT / "scripts" / "classifier_metrics.py",
}

# Cap the in-memory log tail so a long run can't grow unbounded.
_LOG_TAIL_MAX = 300

JobStatus = Literal["running", "succeeded", "failed", "cancelled"]


class JobBusyError(RuntimeError):
    """Raised by `start` when another job is already running."""

    def __init__(self, running_job_id: str) -> None:
        super().__init__(f"another evaluation job is running: {running_job_id}")
        self.running_job_id = running_job_id


class JobProgress(BaseModel):
    done: int = 0
    total: int = 0
    phase: str = "starting"  # starting | seeding | running | done


class Job(BaseModel):
    id: str
    experiment_id: str
    title: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = "running"
    progress: JobProgress = Field(default_factory=JobProgress)
    created_ts: float = Field(default_factory=time.time)
    started_ts: float | None = None
    finished_ts: float | None = None
    returncode: int | None = None
    error: str | None = None
    # Lifecycle events of interest (run_start / run_done) for the UI.
    summary: dict[str, Any] | None = None
    # Result files, relative to `eval/` (e.g. "experiments/results-no_rag-...json").
    result_files: list[str] = Field(default_factory=list)
    log_tail: list[str] = Field(default_factory=list)


class JobManager:
    """Owns the one active job (if any) and a small in-memory history."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._current_id: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task[None] | None = None
        self._cancel_requested = False
        self._logbuf: deque[str] = deque(maxlen=_LOG_TAIL_MAX)

    # ---------- public API ----------

    def is_busy(self) -> bool:
        cur = self.current()
        return cur is not None and cur.status == "running"

    def current(self) -> Job | None:
        return self._jobs.get(self._current_id) if self._current_id else None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        ids = self._order[-limit:][::-1]
        return [self._jobs[i] for i in ids if i in self._jobs]

    async def start(self, experiment: Experiment, params: dict[str, Any]) -> Job:
        """Validate params, create a job, and launch it in the background.

        Raises `JobBusyError` if a job is already running, `ValueError` for
        bad params, or `RuntimeError` if the experiment isn't runnable.
        """
        if self.is_busy():
            raise JobBusyError(self._current_id or "?")
        if experiment.status != "runnable" or experiment.script is None:
            raise RuntimeError(f"experiment {experiment.id!r} is not runnable")

        # Validates ranges/types; raises ValueError before we create the job.
        argv = experiment.build_command_args(params)

        job = Job(
            id=uuid.uuid4().hex[:12],
            experiment_id=experiment.id,
            title=experiment.title,
            params=dict(params or {}),
            started_ts=time.time(),
        )
        self._jobs[job.id] = job
        self._order.append(job.id)
        self._current_id = job.id
        self._cancel_requested = False
        self._logbuf = deque(maxlen=_LOG_TAIL_MAX)
        self._task = asyncio.create_task(self._run(job, experiment, argv))
        return job

    async def cancel(self, job_id: str) -> bool:
        """Terminate a running job. Returns True if a cancel was issued."""
        job = self._jobs.get(job_id)
        if job is None or job.status != "running":
            return False
        self._cancel_requested = True
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        return True

    # ---------- internals ----------

    def _sandbox_dir(self, job_id: str) -> Path:
        return SANDBOX_ROOT / job_id

    async def _run(self, job: Job, experiment: Experiment, argv: list[str]) -> None:
        sandbox = self._sandbox_dir(job.id)
        try:
            sandbox.mkdir(parents=True, exist_ok=True)
            env = {**os.environ, "CHROMA_PERSIST_DIR": str(sandbox)}

            # `evaluate.py` reads an existing KB, so seed the sandbox first.
            # `memory_evolution` reseeds itself (its --reset uses the same
            # CHROMA_PERSIST_DIR), so we leave it to the script.
            if experiment.script == "evaluate":
                job.progress.phase = "seeding"
                await self._seed_sandbox(env)

            job.progress.phase = "running"
            script_path = _SCRIPT_PATHS[experiment.script]
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                *argv,
                "--progress-json",
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._proc = proc
            assert proc.stdout is not None
            async for raw in proc.stdout:
                self._ingest_line(job, raw.decode("utf-8", "replace").rstrip("\n"))
            rc = await proc.wait()
            job.returncode = rc
            if self._cancel_requested:
                job.status = "cancelled"
            elif rc == 0:
                job.status = "succeeded"
            else:
                job.status = "failed"
                if job.error is None:
                    job.error = f"script exited with code {rc}"
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_ts = time.time()
            job.progress.phase = "done"
            job.log_tail = list(self._logbuf)
            self._proc = None
            if self._current_id == job.id:
                self._current_id = None
            self._cleanup_sandbox(sandbox)
            self._persist(job)

    async def _seed_sandbox(self, env: dict[str, str]) -> None:
        """Seed the sandbox ChromaDB by running the seeder as a subprocess."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "seed_knowledge_base.py"),
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        async for raw in proc.stdout:
            self._logbuf.append("[seed] " + raw.decode("utf-8", "replace").rstrip("\n"))
        rc = await proc.wait()
        if rc != 0:
            raise RuntimeError(f"sandbox seeding failed (exit {rc})")

    def _ingest_line(self, job: Job, line: str) -> None:
        """Fold one child stdout line into job state.

        Lines that parse as JSON with an `event` key drive the progress
        model; everything else is human log output kept in the tail.
        """
        stripped = line.strip()
        event: dict[str, Any] | None = None
        if stripped.startswith("{") and '"event"' in stripped:
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and "event" in parsed:
                    event = parsed
            except json.JSONDecodeError:
                event = None

        if event is None:
            self._logbuf.append(line)
            return

        kind = event.get("event")
        if kind == "run_start":
            job.progress.total = int(event.get("total", 0) or 0)
            job.progress.done = 0
        elif kind == "scenario_done":
            job.progress.done = int(event.get("i", job.progress.done) or 0)
            if not event.get("total") and event.get("n"):
                job.progress.total = int(event["n"])
        elif kind == "run_done":
            job.summary = event.get("summary")
            for key in ("md_path", "json_path"):
                p = event.get(key)
                if p:
                    rel = self._relativize(p)
                    if rel and rel not in job.result_files:
                        job.result_files.append(rel)
        # Keep a compact record of events in the log tail too.
        self._logbuf.append(line)

    @staticmethod
    def _relativize(path_str: str) -> str | None:
        try:
            return str(Path(path_str).resolve().relative_to(EVAL_DIR.resolve()))
        except (ValueError, OSError):
            return None

    @staticmethod
    def _cleanup_sandbox(sandbox: Path) -> None:
        # Best-effort: free the throwaway vector DB. Chroma may keep mmap
        # handles on Windows, so swallow errors.
        try:
            if sandbox.exists():
                shutil.rmtree(sandbox, ignore_errors=True)
        except OSError:
            pass

    @staticmethod
    def _persist(job: Job) -> None:
        try:
            JOBS_DIR.mkdir(parents=True, exist_ok=True)
            (JOBS_DIR / f"{job.id}.json").write_text(
                job.model_dump_json(indent=2), encoding="utf-8"
            )
        except OSError:
            pass


# Module-level singleton used by the routes.
job_manager = JobManager()
