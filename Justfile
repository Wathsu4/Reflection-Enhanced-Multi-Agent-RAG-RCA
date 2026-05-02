# Top-level task runner. Install `just` (https://just.systems) for the
# nicer recipes; if not, the same flow is available via
# `scripts/run-all.sh dev` and friends.

# `just` (no arg) lists available recipes.
default:
    @just --list

# Install dependencies for all three sub-projects.
install:
    cd frontend && pnpm install
    cd classifier-service && uv sync
    cd rca-agent-system && uv sync --extra dev

# Seed (or re-seed) the ChromaDB knowledge base. Idempotent.
seed:
    cd rca-agent-system && uv run python scripts/seed_knowledge_base.py

# Run all three services concurrently. Ctrl-C cleans them all up.
# Uses `scripts/run-all.sh` so the same orchestration works without
# `just` installed.
dev:
    bash scripts/run-all.sh dev

# Wipe + reseed memory between demos. Equivalent to the gated
# `/demo/reset-memory` HTTP endpoint without needing the server up.
reset-demo:
    cd rca-agent-system && uv run python scripts/reset_memory.py

# Run all unit/integration tests across the monorepo.
test:
    cd frontend && pnpm test
    cd classifier-service && uv run pytest -q
    cd rca-agent-system && uv run pytest -q

# Production-style frontend build (catches type errors that vitest skips).
build:
    cd frontend && pnpm build

# Pipeline accuracy + latency evaluation. Add `--llm-judge` for the
# Gemini-judged column (slower, costs API quota).
eval *EXTRA:
    cd rca-agent-system && uv run python scripts/evaluate.py {{EXTRA}}

# Memory-evolution evaluation -- the headline novelty experiment.
eval-memory *EXTRA:
    cd rca-agent-system && uv run python scripts/evaluate_memory_evolution.py {{EXTRA}}
