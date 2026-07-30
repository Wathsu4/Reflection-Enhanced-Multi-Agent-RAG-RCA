"""Shared plumbing for the `scripts/` evaluation entry points.

Every eval script needs the same handful of things: the eval output
directories, the `GOOGLE_API_KEY` env bridge, the `--progress-json`
lifecycle emitter the eval-console JobManager tails, a Gemini `ask`
callable, transient-error retries, and (for the ones that run the
pipeline) an in-process ADK Runner. They live here so a change to any of
them lands in one place.

Import order note: scripts must still put the project root on `sys.path`
before importing this module -- it imports `rca_system.settings`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, TypeVar

from rca_system.settings import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / "eval"
# Ablation / baseline runs land here so they never clobber the demo-ready
# `eval/results-*.md` reports (see How-To-Evaluate/PLAN.md decision log).
EXPERIMENTS_DIR = EVAL_DIR / "experiments"
DEFAULT_DATASET = EVAL_DIR / "incidents.jsonl"

APP_NAME = "rca_system"

T = TypeVar("T")

# An `ask` accepts a prompt (and optionally a temperature) and returns the
# model's text. Injected into the metric code so tests need no Gemini key.
AskFn = Callable[..., Awaitable[str]]


def bridge_genai_env() -> None:
    """Export the Gemini credentials from `settings` into `os.environ`.

    ADK's google-genai auth reads `GOOGLE_API_KEY` from the process
    environment, but pydantic-settings only loads it into `settings` (it
    never exports it). Scripts that run the in-process ADK Runner -- via
    CLI or the eval-console subprocess -- need the bridge to
    authenticate. (The HTTP server gets this for free from ADK's own
    .env load.)
    """
    if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    if not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = settings.google_genai_use_vertexai


def emit_progress(enabled: bool, **fields: Any) -> None:
    """Emit one compact JSON lifecycle line to stdout when `--progress-json`
    is set. The eval-console JobManager tails these lines to drive the live
    progress UI. Human-readable logging stays on stderr regardless.

    Each line has an `event` key, one of: run_start, scenario_start,
    scenario_done, run_done.
    """
    if not enabled:
        return
    print(json.dumps(fields, default=str), flush=True)


# -------------------- report output --------------------


def report_target(prefix: str, ablation: str, timestamp: str | None = None) -> tuple[Path, str]:
    """Return `(out_dir, stem)` for a report file.

    Non-default variants are experiments -- keep them out of the
    demo-ready `eval/` reports and tag the filename with the variant.
    """
    timestamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    if ablation == "none":
        return EVAL_DIR, f"{prefix}-{timestamp}"
    return EXPERIMENTS_DIR, f"{prefix}-{ablation}-{timestamp}"


def write_report(out_dir: Path, name: str, content: str) -> Path:
    """Write `content` to `out_dir/name`, creating the directory, and log it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path}", file=sys.stderr)
    return path


# -------------------- Gemini ask --------------------


def make_ask(default_temperature: float = 0.0) -> AskFn:
    """Build an async `ask(prompt, temperature=default)` over google-genai.

    The metric/judge code takes this as an injected callable so it stays
    unit-testable without a Gemini key.
    """
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=settings.google_api_key)

    async def ask(prompt: str, temperature: float | None = None) -> str:
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=default_temperature if temperature is None else temperature
            ),
        )
        return resp.text or ""

    return ask


# -------------------- transient-error retry --------------------

# Substrings that mark a *transient* Gemini failure worth retrying (server
# overload / rate limit), as opposed to a real bug. Matched against the
# captured error string case-insensitively.
_TRANSIENT_MARKERS = (
    "503",
    "unavailable",
    "high demand",
    "429",
    "resource_exhausted",
    "rate limit",
    "deadline",
    "timeout",
)


def is_transient_error(err: str | None) -> bool:
    if not err:
        return False
    low = err.lower()
    return any(m in low for m in _TRANSIENT_MARKERS)


async def run_with_retry(
    run: Callable[[], Awaitable[T]],
    *,
    error_of: Callable[[T], str | None],
    label: str,
    retries: int,
    base_delay: float,
) -> T:
    """Await `run()`, retrying on *transient* Gemini errors with exponential
    backoff. Non-transient errors (and success) return the first attempt.
    This keeps a 503 spike from corrupting the comparison across variants.
    """
    result = await run()
    attempt = 0
    while is_transient_error(error_of(result)) and attempt < retries:
        delay = base_delay * (2**attempt)
        print(
            f"      transient error on {label}; retry "
            f"{attempt + 1}/{retries} in {delay:.0f}s",
            file=sys.stderr,
            flush=True,
        )
        await asyncio.sleep(delay)
        attempt += 1
        result = await run()
    return result


# -------------------- in-process pipeline runner --------------------
# The agent stack is imported lazily so unit tests importing an eval
# script don't pull in ADK (slow, and it wants a Gemini key).


async def stream_pipeline_events(
    log_chunk: str, *, ablation: str, user_id: str
) -> AsyncIterator[Any]:
    """Run a pipeline variant on one log chunk via ADK's in-process Runner
    (no HTTP server needed) and yield its events as they arrive.

    `ablation` selects which wiring to run (see `rca_system.ablations`).
    Exceptions from the run propagate to the caller, which owns how a
    failed scenario is recorded.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    from rca_system.ablations import build_root_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=user_id)
    runner = Runner(
        agent=build_root_agent(ablation),
        app_name=APP_NAME,
        session_service=session_service,
    )
    message = Content(role="user", parts=[Part(text=log_chunk)])

    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=message,
    ):
        yield event


def state_delta(event: Any) -> dict[str, Any]:
    """The `actions.state_delta` an ADK event carries, or `{}`."""
    return getattr(getattr(event, "actions", None), "state_delta", None) or {}
