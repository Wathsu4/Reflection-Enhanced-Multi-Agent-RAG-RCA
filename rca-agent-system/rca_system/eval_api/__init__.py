"""Evaluation console API.

Backs the frontend's `/evaluation` tab: a declarative registry of
experiments (`registry.py`), a single-flight subprocess job runner
(`jobs.py`), and the FastAPI routes that glue them together (`routes.py`).

The registry is the single source of truth -- adding an experiment is a
one-entry change there (plus a script if the experiment is new).
"""

from __future__ import annotations

from rca_system.eval_api.registry import (
    EXPERIMENTS,
    Experiment,
    ParamSpec,
    get_experiment,
    list_experiments,
)

__all__ = [
    "EXPERIMENTS",
    "Experiment",
    "ParamSpec",
    "get_experiment",
    "list_experiments",
]
