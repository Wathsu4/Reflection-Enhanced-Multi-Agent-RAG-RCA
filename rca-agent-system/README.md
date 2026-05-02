# rca-agent-system

Google ADK multi-agent service that performs root-cause analysis on
log chunks flagged by `classifier-service`. A `SequentialAgent`
orchestrates retrieval, reasoning, reflection, and memory-update
sub-agents over a ChromaDB knowledge base whose per-incident
relevance scores adapt over time.

Default port: **8000**. Discovered as ADK app `rca_system`.

## Architecture

```
rca_system/
├── agent.py                 # root_agent = SequentialAgent(...)
├── settings.py              # pydantic-settings: GOOGLE_API_KEY, ports, paths
├── memory/
│   └── chroma_store.py      # IncidentMemory: add / query / update_score / mark_retrieved
├── tools/
│   ├── retrieve_incidents.py        # similarity * success_score re-ranking
│   ├── record_reflection.py         # clamps deltas to [-0.2, +0.2]
│   └── update_memory.py             # apply_reflection_to_memory
└── agents/
    ├── retrieval_agent.py           # output_key="retrieval_output"
    ├── reasoning_agent.py           # output_key="reasoning_output"
    ├── reflection_agent.py          # output_key="reflection_output"
    └── memory_update_agent.py       # output_key="final_output" (Markdown)

server.py                            # FastAPI via ADK get_fast_api_app()
seed/incidents/*.md                  # 6 starter incident records (Phase 6 spec)
scripts/
├── seed_knowledge_base.py           # idempotent
├── reset_memory.py                  # wipe + reseed
├── evaluate.py                      # accuracy + latency on eval dataset
└── evaluate_memory_evolution.py     # headline novelty experiment
eval/
├── incidents.jsonl                  # 15 hand-authored scenarios
└── README.md                        # methodology + how to run
data/                                # gitignored: chroma + sessions.db
```

State propagates between sub-agents via `output_key` writes that ADK
materialises into `session.state`; downstream agents read them via
`{state_key}` template substitution in their instructions (handled
automatically by `inject_session_state`).

## Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)
- A Gemini API key from <https://aistudio.google.com/apikey>

## Install

```bash
uv sync                # runtime deps
uv sync --extra dev    # adds pytest / ruff / pyright / httpx
```

## Configure

```bash
cp .env.example .env
# Edit .env and set:
#   GOOGLE_API_KEY=AIza...
# Optional (default-deny demo helper, see "Endpoints" below):
#   ALLOW_DEMO_RESET=1
```

## Seed the knowledge base

The 6 starter incidents under `seed/incidents/` are loaded into Chroma
with one command. Idempotent — safe to run on every deploy.

```bash
uv run python scripts/seed_knowledge_base.py
# → "Seeded 6 incident(s). Collection now contains 6 entries."
```

## Run

```bash
# Production-style HTTP API (used by the frontend):
uv run python server.py

# Or, ADK's debug web UI (prints to stdout, useful for trace inspection):
uv run adk web
```

Wait for `Application startup complete.` then:

```bash
curl http://localhost:8000/health
# {"status":"ok","model":"gemini-2.5-flash"}

curl http://localhost:8000/list-apps
# ["rca_system"]
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | `{status, model}` — used by the frontend's pill. |
| GET | `/list-apps` | `["rca_system"]` — exactly one entry; ADK noise filtered out. |
| POST | `/apps/rca_system/users/{user}/sessions/{id}` | Create an ADK session. |
| GET | `/apps/rca_system/users/{user}/sessions/{id}` | Fetch a saved session for replay. |
| POST | `/run` | Run the agent and return all events at once. |
| POST | `/run_sse` | Run the agent and stream events as SSE. |
| POST | `/demo/reset-memory` | Wipe + reseed Chroma. **Gated** by `ALLOW_DEMO_RESET=1`. |

## Tests

```bash
uv run pytest -q
# → 85+ tests across chroma_store, tools, agents, pipeline composition,
#   server routes, evaluator helpers.
```

The pipeline composition tests (`tests/test_pipeline.py`) assert
sub-agent ordering, `output_key` contracts, and that each agent's
instruction only references upstream state keys — catching state-flow
regressions cheaply.

## Evaluation

See [`eval/README.md`](./eval/README.md) for the full methodology.
Quick start:

```bash
uv run python scripts/evaluate.py             # keyword scoring (default)
uv run python scripts/evaluate.py --llm-judge # + Gemini-as-judge
uv run python scripts/evaluate_memory_evolution.py
```

Outputs are written to `eval/results-{timestamp}.{json,md}` and
`eval/memory-evolution-{timestamp}.md`.

## Common issues

- **`/health` returns `{status:"ok"}` without `model`**: ADK 1.32
  registers its own `/health`. We strip it in `server.py` and
  re-register a richer one. If a future ADK upgrade silently re-adds
  it, the test in `tests/test_server.py` will fail.
- **`/list-apps` returns `["rca_system","tests","data",...]`**:
  same deal — ADK's default lists every sibling directory. We filter
  to packages that actually export `root_agent`.
- **`InternalError: ... readonly database`** when running
  `reset_memory.py` from inside another process: chromadb 1.x caches
  client handles process-wide. Call
  `chromadb.api.client.SharedSystemClient.clear_system_cache()`
  before `rmtree` (already done in `scripts/reset_memory.py`).
- **First seed run takes ~60s**: chromadb downloads its default
  embedding model (`all-MiniLM-L6-v2`, ~90 MB) on first use.
  Cached after that.
