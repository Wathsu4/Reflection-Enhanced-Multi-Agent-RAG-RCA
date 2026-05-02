# Reflection-Enhanced Multi-Agent RAG for Automated Root-Cause Analysis

A research prototype that pairs a cheap log-severity classifier with a
multi-agent RAG pipeline whose memory of past incidents adapts over
time via reflective feedback.

## What it does

```
log chunks
   │
   ▼
classifier-service (ModernBERT, ~50ms/chunk)
   │   should_invoke_rca = true ?
   │       no  ─────►  drop
   │       yes ─────►  ▼
   │                rca-agent-system  (Google ADK SequentialAgent)
   │                   1. retrieval_agent     ──► top-k similar past incidents (ChromaDB)
   │                   2. reasoning_agent     ──► structured root-cause hypothesis
   │                   3. reflection_agent    ──► per-incident relevance deltas (-0.2 .. +0.2)
   │                   4. memory_update_agent ──► applies deltas, writes Markdown summary
   │                              │
   ▼                              ▼
frontend (Next.js)  ◄────────  SSE stream
   - /classify          manual classifier playground
   - /agent-explorer    manual single-shot RCA console
   - /monitoring        live simulator with Auto-RCA queue
   - /incidents         history replay
```

The novelty claim: the reflection agent's per-incident scores feed
back into retrieval re-ranking on the next run, so the system biases
toward incidents that have historically been useful — without
retraining anything.

## Repository layout

| Path | What's there |
|---|---|
| [`classifier-service/`](./classifier-service/README.md) | FastAPI on `:8001` wrapping the fine-tuned ModernBERT classifier. |
| [`rca-agent-system/`](./rca-agent-system/README.md) | Google ADK pipeline on `:8000`, ChromaDB knowledge base, evaluation tooling. |
| [`frontend/`](./frontend/README.md) | Next.js 16 app on `:3000` (classifier UI, agent explorer, simulator with auto-RCA, history replay). |
| [`docs/`](./docs/) | Demo runbook (`DEMO.md`), research-question coverage matrix (`RESEARCH_QUESTIONS.md`), screenshots placeholder. |
| [`PROJECT_IMPLEMENTATION_GUIDE.md`](./PROJECT_IMPLEMENTATION_GUIDE.md) | Phase-by-phase implementation plan that this codebase follows. |

## Quick start

Prerequisites: Python ≥ 3.11 + [uv](https://docs.astral.sh/uv/),
Node ≥ 20 + [pnpm](https://pnpm.io), a Gemini API key, and the
fine-tuned classifier model placed at
`classifier-service/models/modernbert-log-severity-v1/` (see that
sub-project's README).

```bash
# 1. install everything
just install                 # or: see scripts/run-all.sh

# 2. configure secrets
cp rca-agent-system/.env.example rca-agent-system/.env
# Edit rca-agent-system/.env and set GOOGLE_API_KEY=...

# 3. seed the knowledge base
just seed                    # or: cd rca-agent-system && uv run python scripts/seed_knowledge_base.py

# 4. run all three services concurrently
just dev                     # or: bash scripts/run-all.sh dev

# 5. open the demo
open http://localhost:3000
```

Then follow [`docs/DEMO.md`](./docs/DEMO.md) for the five-act demo
walkthrough.

## Tests

```bash
just test
```

Runs the full test suite across all three sub-projects:

| Layer | Tests | Notes |
|---|---|---|
| Frontend (vitest + Testing Library) | 145+ | Component, hook, and API-client tests. No live network. |
| Classifier service (pytest) | 9+ | FastAPI route tests, model-load smoke. |
| RCA agent system (pytest) | 85+ | ChromaDB / tools / agents / pipeline composition / evaluation helpers. |

## Evaluation

```bash
just eval                       # accuracy + latency on the eval dataset
just eval --llm-judge           # add a Gemini-as-judge column (slower, costs quota)
just eval-memory                # the headline memory-evolution experiment
```

Outputs land under `rca-agent-system/eval/` as both JSON (full per-
scenario records) and Markdown (thesis-ready summary tables).

See [`rca-agent-system/eval/README.md`](./rca-agent-system/eval/README.md)
for the full evaluation methodology and
[`docs/RESEARCH_QUESTIONS.md`](./docs/RESEARCH_QUESTIONS.md) for how
each research question maps onto a code path + an evaluation
artefact.

## Resetting state between demos

Score drift accumulates across runs (that's the whole point), so
between back-to-back demos:

```bash
just reset-demo
```

…or hit the gated HTTP endpoint while the agent service is up:

```bash
ALLOW_DEMO_RESET=1 uv run python rca-agent-system/server.py   # one terminal
curl -X POST http://localhost:8000/demo/reset-memory          # another
```

## License & status

Research prototype for a thesis project. No license set.

The implementation follows the phased plan in
[`PROJECT_IMPLEMENTATION_GUIDE.md`](./PROJECT_IMPLEMENTATION_GUIDE.md);
phases 0–10 are complete.
