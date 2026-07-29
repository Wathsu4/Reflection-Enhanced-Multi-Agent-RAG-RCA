# AGENTS.md

Operational guide for AI coding agents (Devin, Claude, Cursor, etc.)
working in this repository. Read this **first**; it captures the
project-specific information you need to make non-stupid edits without
re-discovering the codebase on every task.

If something in this file is wrong, **fix it** as part of your task —
the file is meant to evolve with the project.

---

## 1. What this project is, in 30 seconds

A research prototype for **automated root-cause analysis (RCA) of
production log streams**. Three independently-deployable services plus
a fine-tuned classifier model:

```
log chunks ──► classifier-service (ModernBERT, :8001, ~50 ms/chunk)
                                │
                                │ should_invoke_rca?
                                ▼
                      rca-agent-system (ADK SequentialAgent, :8000)
                            ├─ 1. retrieval_agent   ──► ChromaDB
                            ├─ 2. reasoning_agent   ──► Gemini 2.5 Flash
                            ├─ 3. reflection_agent  ──► per-incident deltas [-0.2, +0.2]
                            └─ 4. memory_update     ──► applies deltas, writes report
                                │
                                ▼ SSE
                          frontend (Next.js 16, :3000)
                            /classify  /agent-explorer  /monitoring  /incidents
```

The **novelty contribution** is in the orange path (reflection → memory
update → biased retrieval on next run). Memory adapts without
retraining anything. See `docs/ARCHITECTURE_OVERVIEW.md` for the diagram.

Status: research prototype, phases 0–10 of `PROJECT_IMPLEMENTATION_GUIDE.md` complete.

---

## 2. Repo layout

```
.
├── classifier-service/          FastAPI on :8001 — ModernBERT inference (Python ≥3.11, uv)
├── rca-agent-system/            FastAPI/ADK on :8000 — 4-agent pipeline + ChromaDB (Python ≥3.11, uv)
├── frontend/                    Next.js 16 / React 19 on :3000 (pnpm)
├── docs/                        DEFENSE_GUIDE.md, DEMO.md, RESEARCH_QUESTIONS.md, ARCHITECTURE_OVERVIEW.md
├── helpful_scripts/             Stdlib-only utilities + Q&A practice bank (defense_qa.md)
├── scripts/run-all.sh           Process orchestrator used by `just dev` (works without `just`)
├── Justfile                     Top-level recipes (install, seed, dev, test, eval, reset-demo)
├── log_severity_classifier_modernbert.ipynb   Training notebook (Colab, ModernBERT fine-tune on BGL)
├── PROJECT_IMPLEMENTATION_GUIDE.md            Phase-by-phase implementation plan
└── README.md / .env.example
```

Each Python sub-project is a **standalone uv project** with its own
`pyproject.toml`, `.venv`, and `.env.example`. The repo is a monorepo
by convention, not by tooling — there is no top-level Python project.

---

## 3. Common commands

All commands run from the **repo root** unless noted. `just` recipes are
the canonical interface; the same flows are available via
`scripts/run-all.sh` or direct `uv`/`pnpm` calls.

### One-shot setup

```bash
# Install everything (frontend pnpm + both Python services via uv)
just install
# Equivalent:
#   cd frontend && pnpm install
#   cd classifier-service && uv sync --extra dev
#   cd rca-agent-system && uv sync --extra dev

# Configure secrets
cp rca-agent-system/.env.example rca-agent-system/.env
# Then set GOOGLE_API_KEY=... in that file.

# Seed the knowledge base (idempotent; downloads ~90 MB embedding model on first run)
just seed
```

> **Always use `--extra dev`** when calling `uv sync` for either Python
> sub-project. The base extra omits `pytest` / `ruff` / `pyright`, and
> you will get "program not found" if you skip it.

### Daily development

```bash
just dev          # all three services concurrently (Ctrl-C cleans them up)
just test         # full test suite across all three sub-projects
just build        # production-style frontend build (catches TS errors vitest skips)
just reset-demo   # wipe + reseed ChromaDB (between demo attempts)
just eval         # accuracy + latency evaluation
just eval --llm-judge       # add Gemini-as-judge column (slower, costs quota)
just eval-memory  # memory-evolution headline experiment
```

### Running individual services

```bash
# Classifier (port 8001)
cd classifier-service && uv run uvicorn app.main:app --port 8001 --reload

# Agent system (port 8000)
cd rca-agent-system && uv run python server.py
# alt: uv run adk web   # ADK's built-in debug UI

# Frontend (port 3000)
cd frontend && pnpm dev
```

### Individual test runs

```bash
# Classifier (8 tests; 4 require the fine-tuned model on disk)
cd classifier-service && uv run pytest -q
# Skip model-dependent tests on machines without the model:
#   CLASSIFIER_SKIP_MODEL_TESTS=1 uv run pytest -q

# Agent system (~170 tests; uses FakeEmbeddingFunction so no model download)
cd rca-agent-system && uv run pytest -q

# Frontend (~173 tests; jsdom, no live network)
cd frontend && pnpm test
```

---

## 4. Environment variables

The top-level `.env.example` is the union of all three services'
required vars. In practice you copy each sub-project's
`.env.example` into a per-project `.env` (the loaders are
`pydantic-settings`-based and look in the **sub-project directory**).

| Variable | Default | Service | Notes |
|---|---|---|---|
| `GOOGLE_API_KEY` | _none_ | agent | **Required.** Gemini API key. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` | agent | `TRUE` for Vertex AI, `FALSE` for public Gemini API. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | agent | All four sub-agents share this model. |
| `ADK_PORT` | `8000` | agent | |
| `ADK_CORS_ORIGINS` | `http://localhost:3000` | agent | Comma-separated. |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | agent | Relative to `rca-agent-system/`. |
| `CHROMA_COLLECTION` | `incident_memory` | agent | |
| `SESSION_DB_URL` | `sqlite+aiosqlite:///./data/sessions.db` | agent | **Must** use `sqlite+aiosqlite://` (async driver), not plain `sqlite://`. |
| `ALLOW_DEMO_RESET` | `0` | agent | Set to `1` to expose `POST /demo/reset-memory`. Default-deny because it's destructive. |
| `MAX_NEGATIVE_DELTA_FRACTION` | `0.4` | agent | Tier 0 Phase 1: max fraction of the retrieved set that may receive a negative reflection delta per call. |
| `SCORE_PRIOR_STRENGTH` | `2.0` | agent | Tier 0 Phase 2: initial alpha/beta pseudo-count prior for a fresh incident's score. |
| `DELTA_TO_PSEUDOCOUNT_SCALE` | `0.2` | agent | Tier 0 Phase 2: divisor mapping a clamped delta to a pseudo-count. |
| `EXPLORATION_BONUS_WEIGHT` | `0.1` | agent | Tier 0 Phase 3: weight on the anti-starvation term added to retrieval ranking. |
| `REFLECTION_ENSEMBLE_SIZE` | `3` | agent | Tier 0 Phase 4: number of independent reflection samples aggregated per run; `1` reproduces pre-Tier-0 single-shot behavior. |
| `CLASSIFIER_MODEL_PATH` | `./models/modernbert-log-severity-v1` | classifier | Relative to `classifier-service/`. |
| `CLASSIFIER_DEVICE` | `auto` | classifier | `auto` / `cpu` / `cuda` / `mps` (Apple Silicon). |
| `CLASSIFIER_PORT` | `8001` | classifier | |
| `CLASSIFIER_CORS_ORIGINS` | `http://localhost:3000` | classifier | Comma-separated. |
| `CLASSIFIER_MAX_CHUNK_BYTES` | `500000` | classifier | Per-request size guard. |
| `CLASSIFIER_SKIP_MODEL_TESTS` | _unset_ | classifier | Test-only; skips tests that need the model file. |
| `NEXT_PUBLIC_CLASSIFIER_URL` | `http://localhost:8001` | frontend | |
| `NEXT_PUBLIC_AGENT_URL` | `http://localhost:8000` | frontend | |
| `NEXT_PUBLIC_USE_MOCK` | `false` | frontend | `true` opts into keyword-mock classifier (useful offline). |

**Secrets:** Never commit a real `GOOGLE_API_KEY`. `.env` and
`.env.local` are gitignored. The fine-tuned model is **not in git** —
it lives at `classifier-service/models/modernbert-log-severity-v1/`
and is gitignored (`classifier-service/models/` in `.gitignore`).

---

## 5. `classifier-service/` — ModernBERT FastAPI gate

- **Stack:** FastAPI 0.115+, Uvicorn, transformers 4.48+, torch 2.4+, pydantic 2.9+.
- **Python:** ≥3.11.
- **Entry point:** `app.main:app` (Uvicorn). Eager-loads the model in
  the lifespan hook and runs a one-shot warmup classification to
  remove first-request latency. If the model dir is missing, the
  process exits non-zero on startup.
- **Routes:** `GET /health`, `POST /classify`, `POST /generate-logs`,
  `GET /docs` (Swagger). See `app/routers/`.
- **Model:** Fine-tuned ModernBERT-base, 4-class chunk-level severity
  classifier. Path is `models/modernbert-log-severity-v1/` and must
  contain `config.json`, `model.safetensors`, `tokenizer.json`,
  `tokenizer_config.json`, `training_metadata.json`.
- **Device selection** (`classifier-service/app/classifier.py`): `auto` picks CUDA → MPS → CPU.
  Falls back to CPU if a requested device is unavailable.
- **Tests:** `test_log_generator.py` is pure unit (no model);
  `test_api_smoke.py` is auto-skipped if the model is missing or
  `CLASSIFIER_SKIP_MODEL_TESTS=1` is set.

---

## 6. `rca-agent-system/` — Multi-agent ADK pipeline

- **Stack:** Google ADK (`google-adk`), `google-genai`, FastAPI, ChromaDB, sentence-transformers, SQLAlchemy async (sqlite+aiosqlite).
- **Python:** ≥3.11.
- **Package:** `rca_system/`, exports `root_agent` so ADK discovery
  finds the app as `rca_system`.
- **Pipeline (`rca_system/agent.py`):** `SequentialAgent` with the
  four sub-agents below, in this order. **Reordering breaks state
  flow** — each agent reads keys written by upstream agents via
  ADK's `output_key` convention.

| # | Agent | File | Reads | Writes (`output_key`) | Tools |
|---|---|---|---|---|---|
| 1 | retrieval | `rca_system/agents/retrieval_agent.py` | user message | `retrieval_output` (JSON: query, hits) | `retrieve_incidents` |
| 2 | reasoning | `rca_system/agents/reasoning_agent.py` | `retrieval_output`, user message | `reasoning_output` (JSON: hypothesis, confidence, suggested_actions, evidence, used_incident_ids) | _(none — pure LLM)_ |
| 3 | reflection | `rca_system/agents/reflection_agent.py` | `retrieval_output`, `reasoning_output` | `reflection_output` (JSON: incident_score_deltas, overall_quality, rationale) | `ensemble_reflect` |
| 4 | memory_update | `rca_system/agents/memory_update_agent.py` | `reasoning_output`, `reflection_output` | `final_output` (Markdown report) | `apply_reflection_to_memory` |

- **Tools (`rca_system/tools/`):** `retrieve_incidents.py` re-ranks by
  `similarity * success_score + exploration_bonus` (Tier 0 Phase 3 — a
  small, decaying anti-starvation term so a demoted-but-rarely-retrieved
  incident can't be permanently buried; `settings.exploration_bonus_weight`).
  `record_reflection.py` clamps deltas to `[-0.2, +0.2]` and
  deterministically **gates** them (Tier 0 Phase 1 — a positive delta
  survives only if the incident was actually cited as used; negative
  deltas are capped in count by `settings.max_negative_delta_fraction`;
  exact-zero deltas are always dropped). It's no longer wired directly
  to Gemini as a tool (see the reflection row below) but its gating
  logic (`_gate_deltas`) is reused by `reflection_ensemble.py`, and it
  remains fully unit-tested on its own. `reflection_ensemble.py` (Tier 0
  Phase 4) is the tool `reflection_agent` actually calls: internally
  fans out `settings.reflection_ensemble_size` independent, concurrent
  Gemini samples (`asyncio.gather`), gates each one, and aggregates
  (mean deltas, majority-vote quality) before returning. `update_memory.py`
  hands the (already clamped + gated) delta to `IncidentMemory.update_score`.
- **ChromaDB (`rca_system/memory/chroma_store.py`):**
  PersistentClient, cosine distance, `all-MiniLM-L6-v2` embeddings
  (~90 MB, downloaded on first use). Tests use a `FakeEmbeddingFunction`
  (deterministic SHA-256 → 16-d vector) so CI never has to download.
  Incident metadata includes `success_score` (init 1.0, range
  `(0.0, 2.0)` exclusive), `alpha`/`beta` pseudo-count fields (Tier 0
  Phase 2 — `success_score = 2*alpha/(alpha+beta)`, recomputed by
  `update_score` on every write, not stored independently), `usage_count`,
  `last_used_ts`. The pseudo-count formulation is why the score is
  asymptotically damped (each run's influence shrinks as alpha+beta
  grows) instead of accumulating deltas linearly — see
  `How-To-Improve/TIER0_PLAN.md` §7 for the full derivation.
- **Server (`server.py`):** Uses ADK's `get_fast_api_app()`, then
  **strips ADK's default `/health` and `/list-apps`** so the custom
  implementations win. Routes to remember:
  - `POST /run` and `POST /run_sse` — ADK-mounted, SSE for streaming
  - `POST /apps/rca_system/users/{user}/sessions/{id}` — create/fetch session
  - `POST /demo/reset-memory` — **gated by `ALLOW_DEMO_RESET=1`** (else 403). Wipes ChromaDB and reseeds.
  - `/eval/*` — the evaluation console API (see below), mounted via
    `app.include_router(...)` from `rca_system/eval_api/routes.py`.
- **Seed data:** 14 markdown incidents in `seed/incidents/` (Tier 0
  Phase 5 grew this from the original 6 — redis, jvm, deadlock,
  upstream, tls, disk — by adding 8 more: k8s OOMKill, Kafka consumer
  lag, DB connection-pool exhaustion, expired API key, CDN stale cache,
  load-balancer health-check flapping, Node.js memory leak, stale
  distributed lock). YAML frontmatter + body. `scripts/seed_knowledge_base.py`
  upserts by `incident_id` so re-running is safe.
- **Eval:** 15 scenarios in `eval/incidents.jsonl` (12 in-domain,
  3 out-of-distribution) — the canonical, demo-ready dataset, unchanged
  by the Tier 0 KB expansion. `eval/incidents_tier0_validation.jsonl`
  (31 scenarios: those same 15 plus 2 per new Phase 5 incident) is the
  dataset to use when validating against the full 14-incident KB.
  `scripts/evaluate.py` does keyword-overlap
  scoring (default) or LLM-as-judge with `--llm-judge`, **plus** per-stage
  latency, Gemini token counts, and the retrieval IR triad
  (Recall@k/MRR/nDCG). Both eval scripts accept
  `--ablation {none,reflection_off,memory_frozen,no_rag,cot_only,retrieval_only,react}`
  (variants defined in `rca_system/ablations.py`) and
  `--progress-json` (emit JSONL lifecycle events for the UI). Non-default
  ablations write to `eval/experiments/`; the full system writes to
  `eval/` (demo-ready). `react` is a single **ReAct** agent (adaptive
  retrieval loop, no reflection/memory) — the standard agentic baseline
  (Yao 2022; Roy et al. FSE'24); a different topology, not a pipeline clone,
  so fixed-pipeline retrieval-rank metrics don't apply to it.
  `scripts/evaluate_memory_evolution.py` is the headline novelty experiment
  (score drift across runs); `scripts/evaluate_pairwise.py` and
  `scripts/evaluate_ragas.py` add the bias-mitigated A/B judge and the RAG
  triad.
- **Eval console API (`rca_system/eval_api/`):** browse / re-run /
  inspect experiments from the frontend.
  - `registry.py` — declarative metadata for every experiment (id, title,
    RQ tags, plain + technical descriptions, command, param schema,
    `status` runnable|planned, outputs glob). **Single source of truth**;
    adding an experiment is a one-entry change.
  - `jobs.py` — `JobManager`: **single-flight** subprocess runner. Spawns
    `uv run python scripts/...`, **sandboxes ChromaDB** to
    `data/eval-runs/<job-id>/` (seeded fresh, so the live/demo memory is
    never mutated), tails `--progress-json` output, supports cancel, and
    mirrors job state to `eval/experiments/.jobs/<id>.json`.
  - `routes.py` — `GET /eval/experiments[/{id}]`,
    `POST /eval/experiments/{id}/run` (409 if a job is running),
    `GET /eval/jobs[/{id}]`, `POST /eval/jobs/{id}/cancel`,
    `GET /eval/results/{id}/{file}` (path-traversal-guarded). **Runs are
    not gated** (always allowed) but serialised; reads are always allowed.
- **Tests:** pipeline composition, tools, ChromaDB wrapper, server routes,
  seed/reset scripts, evaluation helpers, ablation factory, and the eval
  console (registry / routes / job lifecycle with a mocked subprocess).
  Tests use FakeEmbeddingFunction so no model downloads.

---

## 7. `frontend/` — Next.js operator UI

- **Stack:** Next.js 16, React 19, Tailwind 4, shadcn/ui + Radix,
  TanStack Query, Vitest 4 + jsdom + Testing Library. No MSW; SSE is
  custom-parsed.
- **App router pages (`frontend/src/app/`):**
  - `/` — landing dashboard
  - `/classify` — manual classifier playground
  - `/agent-explorer` — single-shot RCA console with live SSE
  - `/monitoring` — log simulator + auto-RCA queue for ERROR/FATAL chunks
  - `/incidents` — local history of recent runs (localStorage)
  - `/incidents/[id]` — replay a saved ADK session
  - `/evaluation` — evaluation console: cards for every experiment (grouped
    by RQ/family), rendered from the backend registry
  - `/evaluation/[id]` — per-experiment page: plain + technical description,
    params form, re-run control, polled live progress, results + history
- **API clients (`frontend/src/lib/api/`):**
  - `classifier.ts` — `classify`, `getClassifierHealth`, `generateLogs` + typed error classes; optional keyword-mock fallback (`NEXT_PUBLIC_USE_MOCK=true`).
  - `agents.ts` — `getAgentHealth`, `createSession`, `getSession`, `listSessions`, **`runAgentSSE`** (custom POST-SSE async generator), `parseSseBlock` (exported for tests).
  - `evaluation.ts` — `listExperiments`, `getExperiment`, `runExperiment`, `getJob`, `cancelJob`, `getResult` against the `/eval/*` API. Mirrors `agents.ts` conventions (typed error classes, `fetchJson`, `__test__` exports). Job progress is **polled** (TanStack Query `refetchInterval`), not SSE.
- **Why custom SSE?** ADK's `/run_sse` is **POST with a JSON body**,
  so the browser `EventSource` API (GET-only) does not work. The
  generator uses `fetch` + `ReadableStream.getReader()` + `TextDecoder`,
  splits on `\n\n` blocks, and yields parsed `AdkEvent`s. Pass an
  `AbortSignal` to tear down.
- **Hooks (`frontend/src/lib/hooks/`):** `useAgentStream`,
  `useAgentHealth`, `useClassifierHealth`, `useLogSimulator`,
  `useInvestigationsQueue`. `useAgentStream` is the meaty one: it
  consumes the SSE generator and aggregates raw events into per-author
  groups via a pure `aggregateEvents()` function.
- **Tests:** Vitest + jsdom, colocated `*.test.ts(x)` next to source.
  Direct `vi.mock()` of API modules — no MSW. Setup in
  `vitest.setup.ts` adds `jest-dom` matchers and polyfills
  `ResizeObserver` (Radix) and `scrollIntoView`.
- **`next.config.ts`** sets `allowedDevOrigins: ["127.0.0.1", "localhost"]`
  so HMR works in IDE browser previews (Next 16 default-denies cross-origin HMR).

---

## 8. Conventions

### Python (both services)

- **Package manager:** `uv` is canonical. Don't add a `requirements.txt`;
  edit `pyproject.toml` and run `uv sync --extra dev` (or `uv add` if
  you want the latest minor version).
- **Lint / typecheck:** `ruff` (line-length 100, target `py311`) and
  `pyright` (basic mode). Both configured in each `pyproject.toml`.
- **Pydantic v2** everywhere. Settings use `pydantic-settings`.
- **Async DB:** SQLAlchemy 2.0 async style. Use the `sqlite+aiosqlite`
  driver — plain `sqlite://` will silently fail in ADK's
  `DatabaseSessionService`.
- **Tests:** `pytest` + `pytest-asyncio` (`asyncio_mode=auto`).
  Tests live under each sub-project's `tests/` dir and run via
  `uv run pytest -q`. The agent system's tests inject a
  `FakeEmbeddingFunction` to skip the 90 MB embedding download.

### TypeScript / React

- **Strict TS** (`tsconfig.json`). Use the existing typed clients in
  `src/lib/api/` rather than reaching for `fetch` directly.
- **Components:** shadcn primitives live in `src/components/ui/`;
  app-specific composites in `src/components/`. **Mimic existing
  patterns** before adding new abstractions.
- **Styling:** Tailwind 4 + CVA + `tailwind-merge`. Don't introduce a
  new CSS framework.
- **State / data fetching:** TanStack Query for server state.
  Component state via React `useState` / `useReducer`. No Redux.

### Markdown / docs

- `docs/` is the long-form documentation; `helpful_scripts/` holds
  practice / utility material (e.g. `defense_qa.md`).
- **Mermaid diagrams**: a project skill at
  `.windsurf/skills/mermaid-diagrams.md`
  documents the safe authoring subset that renders on GitHub. Read it
  before drawing diagrams.

### Git

- Conventional commits (`feat(scope): ...`, `fix(scope): ...`,
  `docs: ...`, `chore: ...`).
- Cross-OS line endings are normalised by `.gitattributes`
  (LF for source, CRLF for `.bat` / `.ps1`).

---

## 9. Verification — what to run before claiming "done"

Pick the smallest set that covers your changes. Don't run the world.

| Type of change | Minimum verification |
|---|---|
| Classifier code | `cd classifier-service && uv run pytest -q` |
| Agent code / tools / ChromaDB | `cd rca-agent-system && uv run pytest -q` |
| Frontend component / hook | `cd frontend && pnpm test` (or a focused `pnpm test <pattern>`) |
| Cross-service change | `just test` |
| Frontend types / build readiness | `just build` (Turbopack catches TS errors that vitest skips) |
| Pipeline behavior change | `just test` + `just eval` (and inspect `eval/results-*.md`) |
| Memory / scoring change | `just eval-memory` and check `eval/memory-evolution-*.md` |
| README / docs only | _smoke-render the markdown locally_ |

If you change anything that touches the **agent pipeline composition**,
run `cd rca-agent-system && uv run pytest tests/test_pipeline.py -q` —
it validates the state-flow contract between agents without making
Gemini calls.

---

## 10. Known gotchas (read before they bite you)

1. **ChromaDB cache + mmap, on reset.**
   `chromadb` 1.x keeps clients (and HNSW mmaps) in a process-wide
   cache. Naive `shutil.rmtree` of the persist dir fails:
   - POSIX → next `IncidentMemory()` reads the cached, deleted DB → "readonly database".
   - Windows → `WinError 32` on rmtree (mmap handle still open).
   `scripts/reset_memory.py` handles this with `clear_system_cache() +
   gc.collect() + retry`. **Use it; don't reinvent it.** See
   `rca-agent-system/scripts/reset_memory.py`.

2. **`uv sync` without `--extra dev`** gives you a venv without
   pytest/ruff/pyright. Symptom: `Failed to spawn: pytest, Caused by:
   program not found`. Fix: always pass `--extra dev`.

3. **Async sqlite driver is mandatory.** `SESSION_DB_URL` must start
   with `sqlite+aiosqlite://`. Plain `sqlite://` will silently break
   ADK's session storage.

4. **`GOOGLE_API_KEY` is project-scoped to `rca-agent-system/.env`.**
   The other two services don't need it. Putting it only in a
   top-level `.env` won't work because each sub-project loads its own.

5. **First seed/eval run downloads ~90 MB.** `all-MiniLM-L6-v2` is
   downloaded by `sentence-transformers` the first time
   `IncidentMemory` runs. Tests use `FakeEmbeddingFunction` to skip
   this, but `scripts/seed_knowledge_base.py` does not.

6. **Gemini free-tier rate limits.** ~15 RPM. A full
   `evaluate.py` run uses ~96 calls — budget ~10 min wall time. If you
   hit `429`, slow down or wait.

7. **First classifier request is slow.** The warmup pass in
   `LogSeverityClassifier.__init__` should eliminate this, but if it
   fails silently you'll see ~1 s on the first real classify. Check
   the startup logs for "Warmup pass failed".

8. **Test timer flakes.** The frontend `useLogSimulator` test
   uses **real timers** and tolerates a one-tick off-by-one because
   `waitFor` polling can race against the simulator's interval on
   slow machines. Don't "tighten" the bound back to strict equality —
   commit `9c3958e` already fixed this.

9. **ADK auto-registers `/health` and `/list-apps`.** `server.py`
   removes those routes before mounting the custom versions
   (`rca-agent-system/server.py:69-72`). If you upgrade ADK and
   `test_server.py` starts failing, that's why.

10. **`ALLOW_DEMO_RESET` is default-deny.** `POST /demo/reset-memory`
    returns 403 unless you set the env var to `1`. The Justfile's
    `reset-demo` recipe bypasses HTTP entirely and calls the Python
    function directly, so it always works.

11. **Synthetic logs come from the classifier service, not the
    frontend.** `POST /generate-logs` (classifier) is what backs the
    `/monitoring` page's simulator. The frontend's
    `useLogSimulator` hook calls it on an interval.

12. **The fine-tuned model is not in git.** A fresh checkout has an
    empty `classifier-service/models/` (gitignored). Tests will skip
    cleanly; the service will refuse to start. The training notebook
    `log_severity_classifier_modernbert.ipynb` is for Colab — see
    `classifier-service/README.md`
    for how to obtain or rebuild the model.

---

## 11. Where to look for what (FAQ)

| Question | File |
|---|---|
| Where is the pipeline composed? | `rca-agent-system/rca_system/agent.py` |
| Where is similarity × success_score re-ranking? | `rca-agent-system/rca_system/tools/retrieve_incidents.py` |
| How are reflection deltas clamped? | `rca-agent-system/rca_system/tools/record_reflection.py` |
| Where are HTTP routes for the agent service? | `rca-agent-system/server.py` |
| Where are HTTP routes for the classifier? | `classifier-service/app/main.py` + `app/routers/` |
| How is the model loaded (device, warmup)? | `classifier-service/app/classifier.py` |
| How is SSE consumed in the frontend? | `runAgentSSE` in `frontend/src/lib/api/agents.ts` |
| How does the simulator drive auto-RCA? | `frontend/src/lib/hooks/useLogSimulator.ts` + the `/monitoring` page |
| What does each evaluation script report? | `rca-agent-system/eval/README.md` |
| Demo runbook | `docs/DEMO.md` |
| Setup / defense walk-through | `docs/DEFENSE_GUIDE.md` |
| Research-question coverage matrix | `docs/RESEARCH_QUESTIONS.md` |
| Q&A practice bank (used during defense prep) | `helpful_scripts/defense_qa.md` |
| Visualize dataset labels without running ML | `helpful_scripts/visualize_data_and_labels.py` |

---

## 12. Style / behavioural reminders

These are repo-specific reminders that override generic agent
defaults. They're here because they have caused friction before.

- **Don't add comments unless asked.** Code style is "compact, no
  noise"; the existing files are already commented where it matters.
  If you delete a comment, put it back.
- **Don't write new top-level docs** unless the user asks. Append to
  `AGENTS.md` or the relevant existing doc instead.
- **Don't auto-bump dependencies.** If you need a new package, prefer
  `uv add <pkg>` or `pnpm add <pkg>` rather than editing the lock /
  manifest by hand. Don't upgrade unrelated deps in the same change.
- **Don't run destructive operations without asking.** Specifically:
  `just reset-demo`, `scripts/reset_memory.py`, anything touching
  `data/` under `rca-agent-system/`, and `git push --force`.
- **Prefer running tests early.** All three test suites are fast (seconds, not minutes) and catch regressions cheaply.
- **When responding to the user, cite specific files and line ranges**
  using whatever clickable-reference syntax your harness supports
  (e.g. `<ref_file file="..." />` and `<ref_snippet file="..." lines="A-B" />`
  in Devin / Windsurf). Don't paraphrase locations — point at them.

---

## 13. Living notes (append below)

Anything an agent learns about this project that isn't already
documented above should be appended here, dated, with a one-line
context. Don't overwrite — append.

<!-- Format:
### YYYY-MM-DD — short title
context: ...
note: ...
-->

### 2026-07-28 — google-adk `additional_properties` schema bug with `Optional[list[str]]` params
context: implementing Tier 0 Phase 1 (`How-To-Improve/TIER0_PLAN.md`), adding
`used_incident_ids`/`retrieved_incident_ids: list[str] | None = None` params to
`record_reflection` broke the live pipeline outright.
note: `google-adk==1.32.0` (this repo's pinned version) has a bug — matches
[google/adk-python#5364](https://github.com/google/adk-python/issues/5364) —
where ANY function parameter whose default value fails ADK's
`isinstance(default, annotation)` compatibility check (true for `None` against
`list[str]`, regardless of `Optional[...]` vs `X | None` spelling — Python 3.14
unifies both under `types.UnionType`) forces the tool's *entire* parameter
schema through a `pydantic.TypeAdapter(...).json_schema()` fallback that emits
a snake_case `additional_properties` key instead of `additionalProperties`.
`gemini-2.5-flash` 400s on the unrecognized field ("Unknown name
\"additional_properties\" ... Cannot find field"); `gemini-*-pro` tolerates it
silently, so this is easy to miss if you only smoke-test against pro. The
fallback also corrupts sibling parameters in the same schema (e.g. an
already-working `dict[str, float]` param). If you need an ADK function tool
with an `Optional[...]`/nullable list or dict parameter on this stack: don't
use a plain `FunctionTool(func=...)`. Subclass it and override
`_get_declaration()` with a hand-built schema instead (see
`_RecordReflectionTool` in `rca_system/agents/reflection_agent.py`) — the real
Python function keeps its natural signature for direct callers/tests; only the
Gemini-facing schema needs the workaround.
update (2026-07-28, Tier 0 Phase 4): `_RecordReflectionTool` no longer exists —
`reflection_agent`'s tool is now `ensemble_reflect`
(`rca_system/tools/reflection_ensemble.py`), which sidesteps this whole bug
class a different way: it takes **no Gemini-supplied parameters at all** (only
a `ToolContext`, which ADK excludes from the schema), so there's no
`Optional[...]`-shaped parameter for the bug to attach to. The hand-built-schema
technique described above is still valid and may be needed again for a future
tool that *does* need an optional list/dict parameter.

### 2026-07-28 — Tier 0 Phase 2 changed the ChromaDB incident metadata schema
context: `IncidentRecord` gained `alpha`/`beta` pseudo-count fields
(`rca_system/memory/chroma_store.py`); `success_score` is now derived from
them (`2*alpha/(alpha+beta)`) every time `IncidentMemory.update_score` runs.
note: this is a **breaking change** to on-disk ChromaDB state. Records seeded
before this change have no `alpha`/`beta` metadata; `update_score` falls back
to `settings.score_prior_strength` for missing fields so it won't crash, but
the resulting score can look inconsistent with a pre-existing `success_score`
that was never derived from those defaults. Run `just reset-demo` (or
`uv run python scripts/reset_memory.py`) once after pulling this change —
already the documented, safe, idempotent way to get back to known-good state,
no new tooling needed. Not backfilled on purpose (rejected in
`TIER0_PLAN.md` SS3 as unwarranted complexity for a research prototype's fully
regenerable vector index).

### 2026-07-28 — `retrieve_incidents`'s re-rank only reorders what ChromaDB already selected
context: implementing Tier 0 Phase 3's exploration bonus (anti-starvation term
in `retrieve_incidents.py`), initially assumed the bonus could help a
low-similarity, zeroed-out incident get pulled into the results at all.
note: it can't, and this is architectural, not a bug: `retrieve_incidents`
calls `memory.query(query, k=k)` (ChromaDB's own raw cosine-similarity ANN
search) *first*, then re-ranks only the `k` items that search already
returned. The custom `similarity * success_score + exploration_bonus` formula
never influences *which* items ChromaDB selects, only their *order* within an
already-selected set. So the exploration bonus's real effect is "a
rarely-retrieved incident is more *prominent* among incidents already
competitive on raw similarity for this query," not "a semantically-unrelated
incident can resurface out of nowhere." If a future phase wants the latter, it
would need to change what gets passed to `memory.query`'s `k`, not just the
post-hoc re-rank.

### 2026-07-28 — Tier 0 Phase 4: an ADK function tool can freely fan out its own concurrent Gemini calls
context: implementing multi-sample reflection ensembling
(`rca_system/tools/reflection_ensemble.py`) without changing `root_agent`'s
structure (still exactly 4 named `Agent` sub-agents in `SequentialAgent`).
note: an `async def` ADK `FunctionTool` can accept a `tool_context: ToolContext`
parameter (auto-injected by ADK, excluded from the Gemini-facing schema as a
bonus) and, from inside that one tool call, run its own `asyncio.gather` of
independent raw `google.genai` calls (via `genai.Client(...).aio.models.generate_content`),
fully decoupled from ADK's own `Agent`/`Runner` machinery. This is a much
lighter-weight way to get "N independent LLM samples behind one pipeline slot"
than a custom `BaseAgent` subclass or a `LoopAgent` + aggregator — no changes
to `output_key` propagation, sub-agent count, or `isinstance(agent, Agent)`
checks anywhere. Trade-off: those raw calls bypass ADK's own event-stream
token/usage tracking entirely (see `scripts/evaluate.py`'s
`_apply_reflection_diagnostics`, which now has to fold the tool's
self-reported `_debug.ensemble_total_tokens` back into `stage_tokens`
manually, or that cost is silently invisible to every token-based metric).

### 2026-07-28 — a hardcoded `k` in a test can silently assume "k covers every record"
context: Tier 0 Phase 5 grew `seed/incidents/` from 6 to 14 files;
`tests/test_reset_memory.py` seeds the *real* seed directory (not a small
fixture set) and broke.
note: the test used `mem.query("anything", k=10)` to both look up one specific
record's score and to sweep every record's score post-reset. At 6 total
records this always returned everything; at 14, a top-10 similarity search
over the deterministic-but-arbitrary `FakeEmbeddingFunction` can (and did)
exclude the specific record being asserted on. Fixed by switching both
lookups to `_collection.get(...)` (by id, and unfiltered for the full sweep)
since the test was never actually about ranking. **Any test that reads the
real `seed/incidents/` directory and needs to find or sweep specific records
should use a direct `.get()`, not a `k=N` similarity `.query()`**, unless the
test is specifically about rank order.
