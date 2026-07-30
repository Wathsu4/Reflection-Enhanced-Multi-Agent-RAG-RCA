"""Unit tests for the shared eval-script helpers (`scripts/_eval_common.py`)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._eval_common import (  # noqa: E402
    EVAL_DIR,
    EXPERIMENTS_DIR,
    emit_progress,
    is_transient_error,
    report_target,
    run_with_retry,
    state_delta,
    write_report,
)


def test_emit_progress_writes_one_json_line_when_enabled(capsys):
    emit_progress(True, event="run_start", total=3)
    assert json.loads(capsys.readouterr().out.strip()) == {
        "event": "run_start",
        "total": 3,
    }


def test_emit_progress_is_silent_when_disabled(capsys):
    emit_progress(False, event="run_start")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "err",
    ["503 UNAVAILABLE", "model is overloaded (High demand)", "429 RESOURCE_EXHAUSTED"],
)
def test_is_transient_error_matches_overload_markers(err):
    assert is_transient_error(err)


@pytest.mark.parametrize("err", [None, "", "ValueError: bad schema"])
def test_is_transient_error_ignores_real_failures(err):
    assert not is_transient_error(err)


@pytest.mark.asyncio
async def test_run_with_retry_retries_transient_then_succeeds():
    errors = ["503 unavailable", "503 unavailable", None]
    calls = 0

    async def run() -> str | None:
        nonlocal calls
        err = errors[calls]
        calls += 1
        return err

    out = await run_with_retry(
        run, error_of=lambda r: r, label="s1", retries=3, base_delay=0.0
    )
    assert out is None
    assert calls == 3


@pytest.mark.asyncio
async def test_run_with_retry_does_not_retry_non_transient():
    calls = 0

    async def run() -> str:
        nonlocal calls
        calls += 1
        return "ValueError: bad schema"

    out = await run_with_retry(
        run, error_of=lambda r: r, label="s1", retries=3, base_delay=0.0
    )
    assert out == "ValueError: bad schema"
    assert calls == 1


@pytest.mark.asyncio
async def test_run_with_retry_gives_up_after_retries():
    calls = 0

    async def run() -> str:
        nonlocal calls
        calls += 1
        return "503 unavailable"

    await run_with_retry(
        run, error_of=lambda r: r, label="s1", retries=2, base_delay=0.0
    )
    assert calls == 3  # first attempt + 2 retries


def test_report_target_keeps_full_system_runs_in_eval_dir():
    out_dir, stem = report_target("results", "none", timestamp="20250101-000000")
    assert out_dir == EVAL_DIR
    assert stem == "results-20250101-000000"


def test_report_target_sends_ablations_to_experiments_dir():
    out_dir, stem = report_target("results", "no_rag", timestamp="20250101-000000")
    assert out_dir == EXPERIMENTS_DIR
    assert stem == "results-no_rag-20250101-000000"


def test_write_report_creates_the_directory(tmp_path):
    path = write_report(tmp_path / "nested", "r.md", "# hi\n")
    assert path.read_text(encoding="utf-8") == "# hi\n"


def test_state_delta_defaults_to_empty_dict():
    class Event:
        actions = None

    assert state_delta(Event()) == {}


def test_state_delta_reads_actions_state_delta():
    class Actions:
        state_delta = {"final_output": "md"}

    class Event:
        actions = Actions()

    assert state_delta(Event()) == {"final_output": "md"}
