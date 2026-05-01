# Reflection-Enhanced Multi-Agent RAG with Dynamic Memory for Automated Root-Cause Analysis in Software Incidents

> **Implementation Guide for AI Coding Agents (GitHub Copilot, Cursor, Claude Code, etc.)**
>
> **Project owner:** D.G.W.T. Rathnayake (20APSE4867) · Sabaragamuwa University of Sri Lanka
> **Supervisor:** Mr. GACA Herath
> **Related research proposal:** `Research_Project_Proposal_20APSE4867.pdf`

This document is the single source of truth for implementing the end-to-end system. It is written to be read **sequentially, phase by phase**. An AI coding agent should read this document top-to-bottom, then execute one phase at a time, verifying each phase's acceptance criteria before moving on.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [What Changed Since the Proposal](#2-what-changed-since-the-proposal)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Repository Layout](#5-repository-layout)
6. [Global Conventions](#6-global-conventions)
7. [API & Data Contracts](#7-api--data-contracts)
8. [Implementation Phases (Overview)](#8-implementation-phases-overview)
9. [Phase 0 — Monorepo Skeleton & Conventions](#phase-0--monorepo-skeleton--conventions)
10. [Phase 1 — Frontend Foundation + Classifier Page (UI with Mock)](#phase-1--frontend-foundation--classifier-page-ui-with-mock)
11. [Phase 2 — Classifier FastAPI Service](#phase-2--classifier-fastapi-service)
12. [Phase 3 — Wire Classifier to Frontend](#phase-3--wire-classifier-to-frontend)
13. [Phase 4 — Synthetic Log Generator + Simulator Page](#phase-4--synthetic-log-generator--simulator-page)
14. [Phase 5 — ADK Agent System Foundation](#phase-5--adk-agent-system-foundation)
15. [Phase 6 — RAG Retrieval Agent + ChromaDB Knowledge Base](#phase-6--rag-retrieval-agent--chromadb-knowledge-base)
16. [Phase 7 — Reasoning, Reflection & Memory-Update Agents](#phase-7--reasoning-reflection--memory-update-agents)
17. [Phase 8 — Frontend Pages for the Agent System](#phase-8--frontend-pages-for-the-agent-system)
18. [Phase 9 — End-to-End Automated Pipeline](#phase-9--end-to-end-automated-pipeline)
19. [Phase 10 — Polish, Evaluation & Demo Prep](#phase-10--polish-evaluation--demo-prep)
20. [Appendix A — Synthetic Log Templates](#appendix-a--synthetic-log-templates)
21. [Appendix B — Initial Knowledge Base Seed Documents](#appendix-b--initial-knowledge-base-seed-documents)
22. [Appendix C — Glossary](#appendix-c--glossary)

---

## 1. Project Overview

### 1.1 What this system does

Software incident response teams spend a lot of time reading logs to figure out what went wrong. This project automates that investigation loop.

The system works in two stages:

1. **Triage (fast, local):** A fine-tuned ModernBERT classifier reads a window of log lines (~30 lines ≈ 2 minutes of activity) and classifies it into one of four severity buckets: `FATAL_OR_CRITICAL`, `ERROR`, `WARNING`, `NORMAL`.
2. **Root-Cause Analysis (slow, LLM-driven):** When the classifier flags `ERROR` or `FATAL_OR_CRITICAL`, a Google ADK multi-agent system takes over. Specialized agents retrieve similar past incidents (RAG), generate root-cause hypotheses, critique their own reasoning (reflection), and update a dynamic memory of what worked. The result is an explanation plus recommended actions, with confidence scores.

The UI (Next.js) exists to **showcase** this system — to manually test the classifier, inspect the agents, seed incidents via a synthetic log generator, and watch the automated pipeline run end-to-end.

### 1.2 Core novelty

Compared to typical "RAG over incident tickets" approaches:

- **Reflection:** Agents score the usefulness of retrieved context after each RCA run.
- **Dynamic memory:** The ChromaDB vector store reweights entries based on reflection feedback — entries that led to correct diagnoses get boosted; noisy entries get demoted.
- **Multi-agent coordination:** Retrieval, reasoning, reflection, and memory-update are separate ADK agents orchestrated via workflow agents (`SequentialAgent`, `LoopAgent`), not a single monolithic LLM call.

### 1.3 Scope for this implementation

This document covers a **functional prototype** suitable for academic evaluation and demo. It is **not** production-grade; deployment, multi-tenant auth, PII redaction, and horizontal scaling are out of scope.

---

## 2. What Changed Since the Proposal

The research proposal (`Research_Project_Proposal_20APSE4867.pdf`) mentions a few things that have since been revised. This implementation reflects the current plan.

| Area | Proposal said | Implementation uses | Reason |
|---|---|---|---|
| Agent framework | LangGraph | **Google ADK** | Stronger native multi-agent primitives, Vertex AI/Gemini integration, built-in FastAPI + session management |
| LLM | OpenAI GPT | **Gemini** (via ADK) | Natural fit for ADK, free tier for development |
| Vector DB | Pinecone | **ChromaDB** (local) | Zero-setup, runs alongside the agent service, ideal for local demo |
| Triage layer | Not mentioned in proposal | **ModernBERT severity classifier** | Added as a cheap, fast gate so expensive LLM agents only run on real incidents |

The research questions, objectives, and overall methodology from the proposal remain valid — the tooling changes are implementation details, not conceptual ones. When writing the final thesis, these changes should be documented in the Methodology chapter.

---

## 3. System Architecture

### 3.1 High-level diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BROWSER (Next.js, :3000)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ /classifier  │  │ /simulator   │  │ /agents      │  │ /incidents   │ │
│  │ (manual)     │  │ (automated)  │  │ (RCA test)   │  │ (history)    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
          │  POST /classify │                 │  /run_sse       │
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌────────────────────────────────────┐   ┌────────────────────────────────┐
│ classifier-service (FastAPI :8001) │   │ rca-agent-system (ADK :8000)   │
│                                    │   │                                │
│  • ModernBERT-base fine-tuned      │   │  RootRCAAgent (SequentialAgent)│
│  • 4-class severity head           │   │    ├── RetrievalAgent  ────┐   │
│  • GPU or CPU inference            │   │    ├── ReasoningAgent      │   │
│  • POST /classify                  │   │    ├── ReflectionAgent     │   │
│  • POST /generate-logs (synthetic) │   │    └── MemoryUpdateAgent   │   │
└────────────────────────────────────┘   │                            │   │
                                         │                            ▼   │
                                         │                    ┌──────────┐│
                                         │                    │ ChromaDB ││
                                         │                    │ (local)  ││
                                         │                    └──────────┘│
                                         └────────────────────────────────┘
```

### 3.2 Data flow — automated mode

When the simulator is running in automated mode, each tick follows this path:

1. Frontend asks classifier-service for a synthetic log chunk (`POST /generate-logs`).
2. Frontend sends that chunk to the classifier (`POST /classify`).
3. Classifier returns `{severity, confidence, should_invoke_rca}`.
4. If `should_invoke_rca == true`, frontend opens an SSE stream to the ADK agent service (`POST /run_sse`) with the log chunk as the user message.
5. ADK's `RootRCAAgent` runs its sub-agents in sequence; each agent emits events that stream back to the browser.
6. Frontend renders per-agent progress (retrieval hits, hypothesis, reflection critique, final answer).
7. Final RCA result is persisted to local history (`sessions.db` via ADK's `DatabaseSessionService`).

### 3.3 Why a classifier in front of the agents?

LLM calls are expensive and slow. 99% of log windows are `NORMAL`. A cheap, fast local classifier lets the system process a continuous log stream while only invoking the expensive RCA pipeline when something actually went wrong. This mirrors how real SRE tools work — alerts gate human attention, classifiers gate LLM attention.

---

## 4. Technology Stack

| Layer | Technology | Version hint |
|---|---|---|
| Frontend framework | Next.js (App Router) | 15.x |
| Frontend language | TypeScript | 5.x (strict) |
| UI components | shadcn/ui + Tailwind CSS | latest |
| Frontend data fetching | TanStack Query (React Query) | 5.x |
| Frontend icons | lucide-react | latest |
| Classifier runtime | Python + FastAPI + Uvicorn | Py 3.11+, FastAPI 0.115+ |
| ML framework | PyTorch + Hugging Face Transformers | torch 2.x, transformers ≥4.48 |
| Classifier model | `answerdotai/ModernBERT-base` (fine-tuned) | |
| Agent framework | Google ADK (`google-adk`) | latest |
| Agent LLM | Gemini (via ADK) — `gemini-2.5-flash` default | |
| Vector DB | ChromaDB (local, persistent client) | ≥ 0.5 |
| Embeddings for RAG | `sentence-transformers/all-MiniLM-L6-v2` (local) | |
| Agent session store | SQLite via ADK's `DatabaseSessionService` | |
| Python dep manager | `uv` (recommended) or `pip` | |
| Node package manager | `pnpm` (recommended) or `npm` | |

**Why these specific choices:**

- **ModernBERT** — already trained per the provided notebook; supports 8192-token context, which matters because log chunks can be long.
- **Gemini + ADK** — ADK's multi-agent primitives (SequentialAgent, LoopAgent, AgentTool) make the reflection loop clean to express; Gemini has a generous free tier for development.
- **ChromaDB local** — no external service dependency, persists to disk, supports metadata filtering (we need this for scoring), easy to seed and reset for demos.
- **shadcn/ui** — copy-paste components (not a black-box dep), easily themeable, Tailwind-native, modern look without custom design work.
- **SSE over WebSockets** — ADK natively exposes `/run_sse`; we use it. WebSockets would add complexity without benefit here.

---

## 5. Repository Layout

The user-requested root folder name is long — git-friendly short name is recommended.

```
Reflection-Enhanced-Multi-Agent-RAG-RCA/       ← git repo root (slug)
│
├── README.md                                  ← monorepo overview, quick start
├── PROJECT_IMPLEMENTATION_GUIDE.md            ← THIS DOCUMENT
├── .gitignore                                 ← covers all three sub-projects
├── .env.example                               ← template for env vars
├── docker-compose.yml                         ← (optional, Phase 10) run all three
│
├── frontend/                                  ← Next.js app
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── components.json                        ← shadcn config
│   ├── .env.local.example
│   ├── public/
│   └── src/
│       ├── app/
│       │   ├── layout.tsx                     ← app shell (nav, theme)
│       │   ├── page.tsx                       ← dashboard
│       │   ├── classifier/page.tsx            ← manual classifier test
│       │   ├── simulator/page.tsx             ← log generator + live pipeline
│       │   ├── agents/page.tsx                ← manual RCA agent test
│       │   └── incidents/page.tsx             ← history of RCA runs
│       ├── components/
│       │   ├── ui/                            ← shadcn components
│       │   ├── layout/                        ← Sidebar, TopNav, ThemeToggle
│       │   ├── classifier/                    ← LogInput, SeverityBadge, ConfidenceBars, etc.
│       │   ├── simulator/                     ← LogStream, PipelineTimeline
│       │   └── agents/                        ← AgentTrace, HypothesisCard, ReflectionCard
│       ├── lib/
│       │   ├── api/
│       │   │   ├── classifier.ts              ← classifier-service client
│       │   │   └── agents.ts                  ← ADK client (SSE parsing)
│       │   ├── types.ts                       ← shared types (mirror backend contracts)
│       │   ├── utils.ts                       ← cn(), formatters
│       │   └── hooks/                         ← useClassifier, useAgentStream
│       └── styles/globals.css
│
├── classifier-service/                        ← FastAPI + ModernBERT
│   ├── pyproject.toml                         ← or requirements.txt
│   ├── Dockerfile                             ← (Phase 10)
│   ├── .env.example
│   ├── README.md
│   ├── models/                                ← place trained model here (gitignored)
│   │   └── modernbert-log-severity-v1/
│   │       ├── config.json
│   │       ├── model.safetensors
│   │       ├── tokenizer.json
│   │       ├── ...
│   │       └── training_metadata.json
│   └── app/
│       ├── __init__.py
│       ├── main.py                            ← FastAPI app entry
│       ├── config.py                          ← pydantic settings
│       ├── classifier.py                      ← LogSeverityClassifier (from notebook)
│       ├── log_generator.py                   ← synthetic log templates
│       ├── schemas.py                         ← pydantic request/response models
│       └── routers/
│           ├── classify.py
│           ├── generate.py
│           └── health.py
│
└── rca-agent-system/                          ← Google ADK project
    ├── pyproject.toml
    ├── Dockerfile                             ← (Phase 10)
    ├── .env.example
    ├── README.md
    ├── seed/                                  ← initial knowledge-base documents
    │   └── incidents/
    │       ├── redis_connection_refused.md
    │       ├── oom_heap_exhaustion.md
    │       └── ...
    ├── data/                                  ← runtime artifacts (gitignored)
    │   ├── chroma/                            ← ChromaDB persistent store
    │   └── sessions.db                        ← ADK session store
    ├── scripts/
    │   ├── seed_knowledge_base.py             ← one-time KB bootstrap
    │   └── reset_memory.py                    ← wipe ChromaDB for fresh demo
    └── rca_system/                            ← importable Python package
        ├── __init__.py
        ├── server.py                          ← FastAPI app (uses get_fast_api_app)
        ├── settings.py                        ← env config
        ├── memory/
        │   ├── __init__.py
        │   ├── chroma_store.py                ← ChromaDB wrapper
        │   └── scoring.py                     ← dynamic relevance scoring
        ├── tools/
        │   ├── __init__.py
        │   ├── retrieve_incidents.py          ← RAG retrieval tool
        │   ├── update_memory.py               ← memory mutation tool
        │   └── record_reflection.py           ← reflection scoring tool
        └── agents/
            ├── __init__.py                    ← exports `root_agent` (ADK convention)
            ├── root_agent.py                  ← SequentialAgent orchestrator
            ├── retrieval_agent.py
            ├── reasoning_agent.py
            ├── reflection_agent.py
            └── memory_update_agent.py
```

### 5.1 Why a monorepo (and not separate repos)

- Single `README` and single `git clone` for the whole project.
- Shared type definitions conceptually, even if not literally shared across languages.
- Easier for examiners and supervisors to review.
- Simpler CI/CD path if we add it later.

Each sub-project (`frontend/`, `classifier-service/`, `rca-agent-system/`) has its own dependency manifest and can be developed/run in isolation. There is no npm workspaces or cross-linking — they talk to each other only over HTTP.

---

## 6. Global Conventions

### 6.1 Ports

| Service | Port | Why |
|---|---|---|
| Next.js dev server | `3000` | default |
| classifier-service | `8001` | avoid colliding with ADK default |
| rca-agent-system (ADK) | `8000` | ADK's default, keeps `adk web` / `adk api_server` commands simple |
| ChromaDB | embedded (no port) | runs in-process inside `rca-agent-system` |

### 6.2 Environment variables

All env vars live in `.env` files per sub-project, **never committed**. Each sub-project has a `.env.example` checked in that documents required keys with dummy values.

Monorepo root `.env.example` is a convenience — lists all env vars across projects — but each service also has its own for isolated deployment.

### 6.3 Severity enum

Used identically in all three sub-projects:

```
FATAL_OR_CRITICAL  (id=0, priority="critical")
ERROR              (id=1, priority="high")
WARNING            (id=2, priority="low")
NORMAL             (id=3, priority="none")
```

`should_invoke_rca = severity in {FATAL_OR_CRITICAL, ERROR}`.

The frontend must import this enum from a single location (`frontend/src/lib/types.ts`) and never duplicate the mapping inline.

### 6.4 Log chunk format

A "log chunk" is a newline-joined string of log lines. Trailing newlines are stripped. No special framing characters. Example:

```
2024-01-15 10:23:45 INFO  Starting scheduled backup process
2024-01-15 10:23:46 INFO  Backup: 142 files, 1.2GB total
2024-01-15 10:23:52 INFO  Backup completed in 6.1s
```

All three services use this exact convention. The classifier internally tokenizes to ≤ 2048 tokens (see `MAX_SEQ_LENGTH` in the notebook).

### 6.5 Code style

- **Python:** `ruff` for lint + format, `pyright` in basic mode for type-check. Target Python 3.11+. Type-hint everything public.
- **TypeScript:** `strict: true`, ESLint with `@next/eslint-plugin-next`, Prettier. No `any` without a `// eslint-disable-next-line` comment explaining why.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`). Prefix with phase number for clarity, e.g. `feat(phase-2): add /classify endpoint`.

### 6.6 Logging

- Backend services log to stdout as JSON lines (one event per line) so they're trivially parseable. Use `structlog` or plain `logging` with a JSON formatter.
- Frontend logs only to the browser console, and only in dev.

### 6.7 CORS

Both backend services must allow `http://localhost:3000` as an origin during development. FastAPI's `CORSMiddleware` handles this; ADK's `get_fast_api_app` accepts an `allow_origins` parameter. Do **not** use `allow_origins=["*"]` in checked-in code — it masks CORS bugs. Read from env.

---

## 7. API & Data Contracts

These contracts are **frozen** once Phase 2 ships. Frontend and backend evolve together — any contract change must update both sides and this document in the same commit.

### 7.1 `classifier-service` — `POST /classify`

**Request:**
```json
{
  "log_chunk": "2024-01-15 10:23:45 INFO Starting backup\n2024-01-15 10:23:46 ERROR Connection refused"
}
```

**Response (200 OK):**
```json
{
  "severity": "ERROR",
  "severity_id": 1,
  "confidence": 0.9731,
  "should_invoke_rca": true,
  "priority": "high",
  "inference_ms": 48.2,
  "all_probabilities": {
    "FATAL_OR_CRITICAL": 0.0123,
    "ERROR": 0.9731,
    "WARNING": 0.0121,
    "NORMAL": 0.0025
  }
}
```

**Errors:**
- `400` — empty `log_chunk`
- `413` — `log_chunk` exceeds 500 KB (sanity guard)
- `500` — model/inference error (return `{detail: "..."}`)

### 7.2 `classifier-service` — `POST /generate-logs`

Used by the simulator to produce synthetic log chunks on demand. Templates live server-side (see Appendix A) so frontend stays lean.

**Request:**
```json
{
  "profile": "mixed",            // one of: "normal", "warning", "error", "fatal", "mixed"
  "num_lines": 30,
  "seed": null                    // optional int for reproducibility
}
```

**Response (200 OK):**
```json
{
  "log_chunk": "2024-01-15 10:23:45 INFO ...\n...",
  "intended_severity": "ERROR",   // what the template was designed to produce; useful for UI
  "num_lines": 30
}
```

If `profile == "mixed"`, the server picks a weighted-random profile: 70% `normal`, 15% `warning`, 12% `error`, 3% `fatal`. This roughly mirrors real production traffic and makes the automation demo visually interesting without flooding the RCA pipeline.

### 7.3 `classifier-service` — `GET /health`

Returns `{ "status": "ok", "model_loaded": true, "device": "cuda" | "cpu" }`. Used by frontend to show service status.

### 7.4 `rca-agent-system` — ADK-standard endpoints

ADK's `get_fast_api_app()` exposes these automatically. We **don't write them** — we consume them.

| Endpoint | Purpose |
|---|---|
| `POST /apps/{app_name}/users/{user_id}/sessions/{session_id}` | Create a session (required before calling /run) |
| `GET /apps/{app_name}/users/{user_id}/sessions/{session_id}` | Fetch session state and event history |
| `DELETE /apps/{app_name}/users/{user_id}/sessions/{session_id}` | End a session |
| `POST /run` | Run the agent; returns all events as JSON array when done |
| `POST /run_sse` | Run the agent; streams events as Server-Sent Events |
| `GET /list-apps` | List available agent apps |

For our purposes `app_name` is `"rca_system"` (matches the package folder name). `user_id` can be a stable demo string like `"demo-user"`. `session_id` should be a new UUID per RCA invocation.

**`POST /run_sse` request body:**
```json
{
  "app_name": "rca_system",
  "user_id": "demo-user",
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "new_message": {
    "parts": [{ "text": "Analyze this log chunk and identify root cause:\n\n<log_chunk>\n..." }],
    "role": "user"
  },
  "streaming": true
}
```

**Event stream format** — each SSE `data:` line is a JSON object representing one ADK event. Frontend inspects `event.author` (which agent produced it) and `event.content.parts[*].text` (the actual message) to render the timeline. Tool calls surface as events with `function_call` or `function_response` parts.

### 7.5 Shared TypeScript types

Defined once in `frontend/src/lib/types.ts`:

```ts
export type Severity = "FATAL_OR_CRITICAL" | "ERROR" | "WARNING" | "NORMAL";
export type Priority = "critical" | "high" | "low" | "none";

export interface ClassifyResponse {
  severity: Severity;
  severity_id: 0 | 1 | 2 | 3;
  confidence: number;
  should_invoke_rca: boolean;
  priority: Priority;
  inference_ms: number;
  all_probabilities: Record<Severity, number>;
}

export interface GenerateLogsResponse {
  log_chunk: string;
  intended_severity: Severity;
  num_lines: number;
}

// ADK event (partial — only fields we care about)
export interface AdkEvent {
  id: string;
  author: string;              // agent name
  timestamp: number;
  content?: {
    parts: Array<{
      text?: string;
      function_call?: { name: string; args: Record<string, unknown> };
      function_response?: { name: string; response: unknown };
    }>;
    role: "user" | "model";
  };
  actions?: Record<string, unknown>;
}
```

---

## 8. Implementation Phases (Overview)

| Phase | Title | Depends on | Primary deliverable |
|---|---|---|---|
| 0 | Monorepo Skeleton & Conventions | — | Git repo with 3 sub-project folders, .env.example files, README stub |
| 1 | Frontend Foundation + Classifier Page (UI with Mock) | 0 | Next.js app with nav, classifier page, mocked classifier response |
| 2 | Classifier FastAPI Service | 0 | `/classify` and `/health` endpoints working against the trained model |
| 3 | Wire Classifier to Frontend | 1, 2 | Classifier page hits real backend; error states handled |
| 4 | Synthetic Log Generator + Simulator Page | 3 | Simulator page streams synthetic logs through real classifier |
| 5 | ADK Agent System Foundation | 0 | Minimal root agent running via `adk web`; Gemini auth verified |
| 6 | RAG Retrieval Agent + ChromaDB Knowledge Base | 5 | Retrieval agent returns relevant past incidents; KB seeded |
| 7 | Reasoning, Reflection & Memory-Update Agents | 6 | Full RCA pipeline produces hypothesis + critique + memory update |
| 8 | Frontend Pages for the Agent System | 7 | `/agents` page; live streaming via SSE; agent timeline UI |
| 9 | End-to-End Automated Pipeline | 4, 8 | Simulator auto-invokes RCA on `ERROR`/`FATAL`; unified view |
| 10 | Polish, Evaluation & Demo Prep | 9 | Evaluation scripts, demo script, screenshots, final README |

The rest of this document gives each phase its own section with: **Goal**, **Prerequisites**, **Deliverables**, **Tasks**, **Key code**, **Acceptance criteria**, **Gotchas**.

---

## Phase 0 — Monorepo Skeleton & Conventions

### Goal
Create the empty scaffolding so every subsequent phase has a predictable place to drop code.

### Prerequisites
- Node.js ≥ 20 LTS installed.
- Python ≥ 3.11 installed.
- `uv` installed (`pip install uv`) — recommended for fast dependency resolution in the Python sub-projects.
- `pnpm` installed (`npm install -g pnpm`) — recommended for the frontend.
- Git installed.

### Deliverables
- Git repository initialized with three sub-project directories.
- Root-level `README.md`, `.gitignore`, `.env.example`.
- This implementation guide (`PROJECT_IMPLEMENTATION_GUIDE.md`) committed to the repo.

### Tasks

1. **Create the repo.** Suggested slug: `reflection-rca`. Full human-readable name can live in the `README.md` title.
   ```bash
   mkdir reflection-rca && cd reflection-rca
   git init
   ```

2. **Create sub-project directories (empty for now):**
   ```bash
   mkdir -p frontend classifier-service rca-agent-system
   ```

3. **Write the root `.gitignore`.** Must cover Python, Node, and ML artifacts. Minimum contents:
   ```gitignore
   # Python
   __pycache__/
   *.py[cod]
   .venv/
   venv/
   .env
   *.egg-info/
   .pytest_cache/
   .ruff_cache/

   # Node
   node_modules/
   .next/
   out/
   .turbo/
   *.tsbuildinfo

   # ML / data
   classifier-service/models/
   rca-agent-system/data/
   rca-agent-system/**/sessions.db

   # IDE / OS
   .vscode/
   .idea/
   .DS_Store
   Thumbs.db

   # Env
   .env
   .env.local
   .env.*.local
   ```

4. **Write the root `README.md`** — a short overview pointing readers to the full guide:
   ```markdown
   # Reflection-Enhanced Multi-Agent RAG with Dynamic Memory for Automated Root-Cause Analysis in Software Incidents

   Final-year research project. See [`PROJECT_IMPLEMENTATION_GUIDE.md`](./PROJECT_IMPLEMENTATION_GUIDE.md) for full implementation details.

   ## Quick start
   See each sub-project's README:
   - [frontend/](./frontend/README.md)
   - [classifier-service/](./classifier-service/README.md)
   - [rca-agent-system/](./rca-agent-system/README.md)

   ## Architecture (summary)
   [short diagram or a link to the guide's architecture section]
   ```

5. **Write the root `.env.example`** — a convenience aggregator:
   ```bash
   # ----- classifier-service -----
   CLASSIFIER_MODEL_PATH=./classifier-service/models/modernbert-log-severity-v1
   CLASSIFIER_DEVICE=auto           # auto | cpu | cuda
   CLASSIFIER_PORT=8001
   CLASSIFIER_CORS_ORIGINS=http://localhost:3000

   # ----- rca-agent-system -----
   GOOGLE_API_KEY=your-gemini-api-key-here
   GOOGLE_GENAI_USE_VERTEXAI=FALSE
   ADK_PORT=8000
   ADK_CORS_ORIGINS=http://localhost:3000
   CHROMA_PERSIST_DIR=./rca-agent-system/data/chroma
   CHROMA_COLLECTION=incident_memory
   SESSION_DB_URL=sqlite+aiosqlite:///./rca-agent-system/data/sessions.db
   GEMINI_MODEL=gemini-2.5-flash

   # ----- frontend -----
   NEXT_PUBLIC_CLASSIFIER_URL=http://localhost:8001
   NEXT_PUBLIC_AGENT_URL=http://localhost:8000
   ```

6. **Commit this `PROJECT_IMPLEMENTATION_GUIDE.md`** to the repo root. The guide itself is a project artifact — every phase of work should begin with a `git pull` and a re-read of the relevant phase.

7. **Initial commit:**
   ```bash
   git add .
   git commit -m "chore(phase-0): scaffold monorepo"
   ```

### Acceptance criteria
- `git status` is clean.
- `ls` shows exactly: `frontend/ classifier-service/ rca-agent-system/ README.md PROJECT_IMPLEMENTATION_GUIDE.md .gitignore .env.example`.
- `.env.example` contains entries for all three sub-projects.

### Gotchas
- **Don't** check in a real `.env` file. Only `.env.example`.
- **Don't** add npm workspaces or pnpm workspaces — the sub-projects are independent by design.

---

## Phase 1 — Frontend Foundation + Classifier Page (UI with Mock)

### Goal
Stand up the Next.js app with navigation, dark-mode support, and a fully functional classifier test page. The page must work end-to-end **with a mocked classifier response** so frontend development isn't blocked by the (not-yet-built) FastAPI service.

### Prerequisites
- Phase 0 complete.

### Deliverables
- Next.js 15 app in `frontend/` using App Router, TypeScript strict mode, Tailwind CSS.
- shadcn/ui initialized; at least `button`, `card`, `textarea`, `badge`, `tabs`, `separator`, `alert` components installed.
- App layout with a left sidebar nav that includes: Dashboard, Classifier, Simulator, Agents, Incidents.
- Dark/light theme toggle (`next-themes`).
- `/classifier` page fully working against a local mock.
- `/` (dashboard) page with placeholder cards linking to each tool.
- Other pages (`/simulator`, `/agents`, `/incidents`) exist as stubs saying "Coming in Phase X".

### Tasks

1. **Scaffold Next.js:**
   ```bash
   cd frontend
   pnpm create next-app@latest . --typescript --tailwind --app --src-dir --import-alias "@/*" --no-eslint --turbopack
   # then:
   pnpm add -D eslint eslint-config-next prettier prettier-plugin-tailwindcss
   pnpm add lucide-react class-variance-authority clsx tailwind-merge
   pnpm add @tanstack/react-query
   pnpm add next-themes
   ```
   Say **No** to Turbopack if you hit issues on your machine; it's optional.

2. **Initialize shadcn/ui:**
   ```bash
   pnpm dlx shadcn@latest init
   # pick: Default style, Slate base color, CSS variables yes
   pnpm dlx shadcn@latest add button card textarea badge tabs separator alert skeleton scroll-area label switch progress
   ```
   This populates `src/components/ui/` and sets `components.json`.

3. **Write `src/lib/utils.ts`** — shadcn will have created this already with `cn()`. Add:
   ```ts
   import { clsx, type ClassValue } from "clsx";
   import { twMerge } from "tailwind-merge";

   export function cn(...inputs: ClassValue[]) {
     return twMerge(clsx(inputs));
   }

   export function formatConfidence(conf: number): string {
     return `${(conf * 100).toFixed(1)}%`;
   }
   ```

4. **Write `src/lib/types.ts`** — copy the block from §7.5 verbatim, plus:
   ```ts
   export const SEVERITY_ORDER: Severity[] = [
     "FATAL_OR_CRITICAL",
     "ERROR",
     "WARNING",
     "NORMAL",
   ];

   export const SEVERITY_COLORS: Record<Severity, string> = {
     FATAL_OR_CRITICAL: "bg-red-600 text-white",
     ERROR: "bg-orange-500 text-white",
     WARNING: "bg-yellow-500 text-black",
     NORMAL: "bg-green-600 text-white",
   };
   ```

5. **Write `src/lib/api/classifier.ts`** — client for the classifier service. For Phase 1 this returns a **mocked** response so the UI works without the backend:
   ```ts
   import type { ClassifyResponse } from "@/lib/types";

   const CLASSIFIER_URL = process.env.NEXT_PUBLIC_CLASSIFIER_URL;
   const USE_MOCK = !CLASSIFIER_URL; // Phase 1: no env var set → mock

   export async function classify(logChunk: string): Promise<ClassifyResponse> {
     if (USE_MOCK) return mockClassify(logChunk);

     const res = await fetch(`${CLASSIFIER_URL}/classify`, {
       method: "POST",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({ log_chunk: logChunk }),
     });
     if (!res.ok) throw new Error(`Classifier error: ${res.status}`);
     return res.json();
   }

   // Naive keyword-based mock. Good enough to exercise the UI.
   function mockClassify(chunk: string): Promise<ClassifyResponse> {
     const lower = chunk.toLowerCase();
     let severity: ClassifyResponse["severity"] = "NORMAL";
     if (/fatal|panic|core dump|out of memory/.test(lower)) severity = "FATAL_OR_CRITICAL";
     else if (/error|exception|failed|refused|5\d\d/.test(lower)) severity = "ERROR";
     else if (/warn|deprecat|retry|slow|latency/.test(lower)) severity = "WARNING";

     const conf = 0.8 + Math.random() * 0.15;
     const probs = { FATAL_OR_CRITICAL: 0, ERROR: 0, WARNING: 0, NORMAL: 0 };
     probs[severity] = conf;
     const remainder = (1 - conf) / 3;
     for (const k of Object.keys(probs) as (keyof typeof probs)[]) {
       if (k !== severity) probs[k] = remainder;
     }

     return new Promise((r) =>
       setTimeout(
         () =>
           r({
             severity,
             severity_id: ["FATAL_OR_CRITICAL", "ERROR", "WARNING", "NORMAL"].indexOf(severity) as 0|1|2|3,
             confidence: conf,
             should_invoke_rca: severity === "FATAL_OR_CRITICAL" || severity === "ERROR",
             priority: severity === "FATAL_OR_CRITICAL" ? "critical" : severity === "ERROR" ? "high" : severity === "WARNING" ? "low" : "none",
             inference_ms: 20 + Math.random() * 60,
             all_probabilities: probs,
           }),
         400 + Math.random() * 400,
       ),
     );
   }
   ```

6. **App shell and nav** — `src/app/layout.tsx`:
   - Wrap with a `ThemeProvider` from `next-themes`.
   - Wrap with a `QueryClientProvider` from TanStack Query (create the client in a client component to avoid SSR issues).
   - Persistent left sidebar (`<aside>`) with nav links using `next/link`. Use lucide-react icons: `LayoutDashboard`, `ScanSearch`, `Activity`, `Bot`, `ClipboardList`.
   - Top bar with app title and the theme toggle.

7. **Dashboard page** (`src/app/page.tsx`) — a simple grid of 4 cards, each linking to one of the tool pages, with a one-line description of what the tool does.

8. **Classifier page** (`src/app/classifier/page.tsx`) — the core of Phase 1. Layout:
   - **Left column (flex-1):** a `Textarea` labeled "Paste log lines here", `min-h-[400px]`, monospace font. Below it, a row with: a "Classify" `Button` (primary, with loading state), a "Load example" `Button` with a dropdown for example templates (normal / warning / error / fatal), and a "Clear" button.
   - **Right column (flex-1):** a results `Card`. Before classification, show an empty state ("Run a classification to see results"). After classification, show:
     - Large `SeverityBadge` (use SEVERITY_COLORS) with the predicted severity.
     - Confidence number formatted as a percentage, with a small `Progress` bar.
     - A stacked bar chart showing all four class probabilities (use shadcn `Progress` or a simple custom div per class — no chart library needed for this).
     - Priority label ("Critical" / "High" / "Low" / "None") and a colored dot.
     - A callout box: "Would trigger RCA pipeline: Yes/No".
     - Inference latency in ms.
   - Use TanStack Query's `useMutation` for the classify call so you get loading / error / success states for free.
   - Error state: if `classify` throws, show a `<Alert variant="destructive">` with the error message and a "Retry" button.

9. **Stub pages:** `/simulator`, `/agents`, `/incidents` — each just renders a card saying "Coming in Phase 4 / 8 / 8" so nav links don't 404.

10. **Styling details:**
    - Sidebar: `w-60`, `border-r`, sticky, full height.
    - Use Tailwind's `font-mono` for anything showing log text.
    - Make the classifier page usable on laptops (≥ 1280px). Mobile responsiveness is not a priority (demo will be on a laptop).

11. **Commit:**
    ```bash
    git add .
    git commit -m "feat(phase-1): frontend foundation with mocked classifier page"
    ```

### Key code — the classifier page (reference implementation)

Rough structure — adapt to your component choices:

```tsx
// src/app/classifier/page.tsx
"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { classify } from "@/lib/api/classifier";
import type { ClassifyResponse } from "@/lib/types";
import { ResultPanel } from "@/components/classifier/ResultPanel";
import { LogInput } from "@/components/classifier/LogInput";

export default function ClassifierPage() {
  const [input, setInput] = useState("");
  const mutation = useMutation({ mutationFn: classify });

  return (
    <div className="flex h-full gap-6 p-6">
      <div className="flex-1">
        <LogInput
          value={input}
          onChange={setInput}
          onClassify={() => mutation.mutate(input)}
          loading={mutation.isPending}
        />
      </div>
      <div className="flex-1">
        <ResultPanel
          result={mutation.data}
          error={mutation.error}
          loading={mutation.isPending}
        />
      </div>
    </div>
  );
}
```

Split further into `LogInput`, `ResultPanel`, `SeverityBadge`, `ProbabilityBars`, `ExampleLoader` components under `src/components/classifier/`.

### Acceptance criteria
- `pnpm dev` starts the app on :3000 with no console errors.
- Nav is visible, all five pages route correctly.
- Theme toggle switches between light/dark.
- On the classifier page: pasting a log chunk with "ERROR" in it and clicking Classify shows an ERROR badge and a plausible-looking probability breakdown, within ~800ms.
- Empty-input submission is blocked (button disabled when input is empty).
- The "Load example" button offers at least 4 presets (one per severity) and populates the textarea.

### Gotchas
- Next.js 15 App Router defaults to Server Components. `useState`/`useMutation` require `"use client"` at the top of files that use them.
- TanStack Query's `QueryClient` must be created in a client component (`src/components/providers.tsx`) and not on the module level, or you'll get hydration errors.
- Don't set `NEXT_PUBLIC_CLASSIFIER_URL` yet — the mock is intentionally the default while the FastAPI service doesn't exist.

---

## Phase 2 — Classifier FastAPI Service

### Goal
Host the fine-tuned ModernBERT model behind a small FastAPI service that implements the `POST /classify`, `POST /generate-logs`, and `GET /health` endpoints exactly as specified in §7.

### Prerequisites
- Phase 0 complete.
- Fine-tuned model directory (from the training notebook) available locally.

### Deliverables
- Python package under `classifier-service/app/`.
- `pyproject.toml` (or `requirements.txt`) with pinned dependencies.
- `classifier-service/README.md` with setup instructions.
- Working service on `:8001` that loads the model on startup and responds correctly to all three endpoints.

### Tasks

1. **Create the Python project:**
   ```bash
   cd classifier-service
   uv init --python 3.11
   uv add fastapi uvicorn[standard] pydantic pydantic-settings
   uv add transformers torch sentencepiece
   uv add --dev ruff pyright pytest httpx
   ```
   If you prefer plain pip: create a venv, then `pip install` the same packages and freeze to `requirements.txt`.

2. **Drop the trained model into the project:**
   ```
   classifier-service/models/modernbert-log-severity-v1/
     config.json
     model.safetensors       (or pytorch_model.bin)
     tokenizer.json
     tokenizer_config.json
     special_tokens_map.json
     training_metadata.json
   ```
   This directory is gitignored. Document in `classifier-service/README.md` that developers need to download it from Google Drive (per the training notebook) and place it here.

3. **Write `app/config.py`:**
   ```python
   from pathlib import Path
   from pydantic_settings import BaseSettings, SettingsConfigDict

   class Settings(BaseSettings):
       model_config = SettingsConfigDict(env_file=".env", env_prefix="CLASSIFIER_", extra="ignore")

       model_path: Path = Path("./models/modernbert-log-severity-v1")
       device: str = "auto"                              # auto | cpu | cuda
       port: int = 8001
       cors_origins: str = "http://localhost:3000"       # comma-separated

       max_chunk_bytes: int = 500_000                    # ~500 KB

       @property
       def cors_origins_list(self) -> list[str]:
           return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

   settings = Settings()
   ```

4. **Write `app/classifier.py`** — port the `LogSeverityClassifier` class from Cell 20 of the training notebook. Key adjustments for a service context:
   - Load model **once** at import time (not per-request).
   - Handle `device="auto"` → prefer CUDA, fall back to CPU.
   - Keep `@torch.no_grad()` on the inference method.
   - Return a plain `dict` matching the response schema in §7.1.
   - Add a simple thread-safety note: the HuggingFace model is safe for concurrent read-only use; no lock needed.

   ```python
   import json
   import time
   from pathlib import Path
   import torch
   from transformers import AutoModelForSequenceClassification, AutoTokenizer

   class LogSeverityClassifier:
       def __init__(self, model_path: Path, device: str = "auto"):
           if device == "auto":
               device = "cuda" if torch.cuda.is_available() else "cpu"
           self.device = device

           meta_path = model_path / "training_metadata.json"
           with meta_path.open() as f:
               meta = json.load(f)
           self.id_to_label: dict[int, str] = {int(k): v for k, v in meta["id_to_label"].items()}
           self.max_length: int = meta["max_seq_length"]

           self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
           self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
           self.model.to(self.device).eval()

       @torch.no_grad()
       def classify(self, log_chunk: str) -> dict:
           t0 = time.perf_counter()
           inputs = self.tokenizer(
               log_chunk, truncation=True, max_length=self.max_length, return_tensors="pt"
           ).to(self.device)
           logits = self.model(**inputs).logits
           probs = torch.softmax(logits, dim=-1)[0]
           pred_id = int(probs.argmax().item())
           confidence = float(probs[pred_id].item())
           severity = self.id_to_label[pred_id]

           priority_map = {"FATAL_OR_CRITICAL": "critical", "ERROR": "high", "WARNING": "low", "NORMAL": "none"}
           return {
               "severity": severity,
               "severity_id": pred_id,
               "confidence": round(confidence, 4),
               "should_invoke_rca": severity in ("FATAL_OR_CRITICAL", "ERROR"),
               "priority": priority_map[severity],
               "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
               "all_probabilities": {
                   self.id_to_label[i]: round(float(probs[i].item()), 4) for i in range(len(probs))
               },
           }
   ```

5. **Write `app/schemas.py`** — Pydantic request/response models matching §7.1 and §7.2. Include the 500 KB size guard as a Pydantic validator on the request body (don't rely on FastAPI's default request size limit).

6. **Write `app/log_generator.py`** — synthetic log templates. See Appendix A for the template catalog. The public API of this module is:
   ```python
   def generate_log_chunk(profile: str, num_lines: int = 30, seed: int | None = None) -> tuple[str, str]:
       """Returns (log_chunk_str, intended_severity)."""
   ```

7. **Write routers:**
   - `app/routers/classify.py` — `POST /classify`, depends on the classifier singleton.
   - `app/routers/generate.py` — `POST /generate-logs`.
   - `app/routers/health.py` — `GET /health`.

8. **Write `app/main.py`:**
   ```python
   from contextlib import asynccontextmanager
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware
   from .classifier import LogSeverityClassifier
   from .config import settings
   from .routers import classify, generate, health

   classifier_singleton: LogSeverityClassifier | None = None

   @asynccontextmanager
   async def lifespan(app: FastAPI):
       global classifier_singleton
       classifier_singleton = LogSeverityClassifier(settings.model_path, settings.device)
       app.state.classifier = classifier_singleton
       yield
       # no teardown needed; torch cleans up on exit

   app = FastAPI(title="Log Severity Classifier", version="1.0.0", lifespan=lifespan)

   app.add_middleware(
       CORSMiddleware,
       allow_origins=settings.cors_origins_list,
       allow_methods=["POST", "GET", "OPTIONS"],
       allow_headers=["*"],
   )

   app.include_router(health.router)
   app.include_router(classify.router)
   app.include_router(generate.router)
   ```

9. **Run it:**
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```
   Visit `http://localhost:8001/docs` to see the auto-generated Swagger UI and test endpoints.

10. **Write a smoke test** (`tests/test_classify.py`):
    ```python
    from fastapi.testclient import TestClient
    from app.main import app

    def test_health():
        with TestClient(app) as client:
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json()["model_loaded"] is True

    def test_classify_error_chunk():
        with TestClient(app) as client:
            chunk = "2024-01-15 ERROR Connection refused to Redis\n" * 5
            r = client.post("/classify", json={"log_chunk": chunk})
            assert r.status_code == 200
            body = r.json()
            assert body["severity"] in ("ERROR", "FATAL_OR_CRITICAL")
            assert body["should_invoke_rca"] is True
    ```

11. **Commit:**
    ```bash
    git add .
    git commit -m "feat(phase-2): classifier FastAPI service with /classify /generate-logs /health"
    ```

### Acceptance criteria
- `uvicorn` starts on :8001 without errors; logs show "model loaded on <device>".
- `GET /health` returns `{status:"ok", model_loaded:true, device:"cpu"|"cuda"}`.
- `POST /classify` with an ERROR-heavy chunk returns `severity:"ERROR"` and `should_invoke_rca:true`.
- `POST /classify` with `log_chunk:""` returns 400.
- `POST /generate-logs` with `profile:"fatal"` returns a chunk containing FATAL/OOM/crash keywords.
- Swagger UI at `/docs` renders.
- `uv run pytest` passes.

### Gotchas
- **Model loading is slow** (several seconds on CPU, ~1s on GPU). Load during FastAPI's `lifespan` startup, not on first request.
- **FP32 vs FP16:** the saved model is FP32. That's fine for inference. Don't try to cast to FP16 on CPU.
- **`tokenizer_config.json` missing `model_max_length`?** The training notebook saves `max_seq_length` in `training_metadata.json` — read from there, don't trust the tokenizer's default.
- **First-request latency:** CUDA warm-up takes time. Consider a dummy `classifier_singleton.classify("warmup")` at the end of `lifespan` startup.
- **CORS preflight (`OPTIONS`):** make sure `CORSMiddleware` is added before any routers. FastAPI processes middleware in reverse registration order.

---

## Phase 3 — Wire Classifier to Frontend

### Goal
Replace the mock in `src/lib/api/classifier.ts` with real HTTP calls and verify that the classifier page in the frontend talks to the FastAPI service.

### Prerequisites
- Phase 1 (frontend up on :3000).
- Phase 2 (classifier-service up on :8001).

### Deliverables
- Frontend `.env.local` with `NEXT_PUBLIC_CLASSIFIER_URL=http://localhost:8001`.
- `classifier.ts` API client with real fetch + error handling.
- A small "service status" indicator in the top nav (green = classifier healthy, red = down).
- Error state in the classifier page handles network failures gracefully.

### Tasks

1. **Set the env var:**
   ```bash
   # frontend/.env.local
   NEXT_PUBLIC_CLASSIFIER_URL=http://localhost:8001
   ```
   Restart `pnpm dev`.

2. **Remove the mock branch from `classifier.ts`** — or keep it behind an explicit `NEXT_PUBLIC_USE_MOCK=true` flag for offline development. Either is fine; the explicit flag is more flexible.

3. **Add a `useHealth` hook** (`src/lib/hooks/useHealth.ts`) that polls `GET /health` every 10s and returns `"ok" | "down" | "loading"`:
   ```ts
   import { useQuery } from "@tanstack/react-query";

   export function useClassifierHealth() {
     return useQuery({
       queryKey: ["classifier-health"],
       queryFn: async () => {
         const url = process.env.NEXT_PUBLIC_CLASSIFIER_URL;
         if (!url) throw new Error("no classifier url");
         const r = await fetch(`${url}/health`);
         if (!r.ok) throw new Error("unhealthy");
         return r.json() as Promise<{ status: string; model_loaded: boolean; device: string }>;
       },
       refetchInterval: 10_000,
       retry: 1,
     });
   }
   ```

4. **Render a status pill** in the top nav:
   ```tsx
   const { data, isError } = useClassifierHealth();
   const status = isError ? "down" : data ? "ok" : "loading";
   // render green/red/gray dot + text
   ```

5. **Improve error handling on the classifier page** — differentiate between:
   - Network error (service down): "Can't reach the classifier service. Is it running on :8001?"
   - HTTP 4xx: show the `detail` field from the response.
   - HTTP 5xx: "Classifier service had an internal error; check its logs."

6. **Manually test:**
   - Stop classifier-service → status pill goes red, Classify button shows a helpful error.
   - Restart → status pill goes green within 10s, classification works.
   - Paste a chunk from the training notebook's demo inputs → verify the severity matches what the notebook predicted.

7. **Commit:**
   ```bash
   git add .
   git commit -m "feat(phase-3): wire frontend to real classifier service"
   ```

### Acceptance criteria
- Classifier page returns real model predictions when the service is up.
- The top nav shows a live health indicator that updates when the service goes up/down.
- Network errors surface a clear error message, not a raw fetch exception.
- No hard-coded `localhost:8001` strings in the frontend — only via the env var.

### Gotchas
- **CORS:** if the browser says "blocked by CORS policy", verify `CLASSIFIER_CORS_ORIGINS` is set and the service was restarted after setting it.
- **Mixed content:** don't deploy frontend over HTTPS while pointing at an HTTP classifier — browsers block it. Local dev is fine because both are HTTP.
- **`NEXT_PUBLIC_*`:** Only env vars prefixed with `NEXT_PUBLIC_` are exposed to the browser. Don't forget the prefix.

---

## Phase 4 — Synthetic Log Generator + Simulator Page

### Goal
Build the simulator page. In this phase it runs a loop that: (1) asks the classifier-service for a synthetic chunk, (2) classifies it, (3) adds the result to a live timeline. The RCA agent invocation is **not yet connected** — that's Phase 9.

### Prerequisites
- Phase 3.

### Deliverables
- Simulator page at `/simulator` with:
  - Controls: Start/Stop button, tick-interval slider (1–10s), profile selector (normal/warning/error/fatal/mixed), lines-per-chunk slider (10–50).
  - Live "log stream" panel that scrolls as new chunks arrive.
  - Live "classifications" timeline showing the last N (say, 50) chunks with their severity and confidence.
  - Summary stats card: total chunks, % ERROR, % FATAL, mean inference ms.
- Backend `POST /generate-logs` endpoint already built in Phase 2 — use it.

### Tasks

1. **Simulator state management.** Use a simple React reducer or Zustand store. Key state:
   ```ts
   interface SimulatorState {
     running: boolean;
     intervalMs: number;
     profile: "normal" | "warning" | "error" | "fatal" | "mixed";
     linesPerChunk: number;
     history: Array<{
       id: string;           // uuid
       timestamp: number;
       chunk: string;
       intendedSeverity: Severity;    // what template was aiming for
       result: ClassifyResponse | null;  // null while in-flight
       error?: string;
     }>;
   }
   ```

2. **Tick loop.** A `useEffect` that, when `running` is true, sets a `setInterval` calling an async function: generate → classify → push to history. Cap history at 50 entries (shift oldest off).

3. **LogStream component.** Displays the raw log text of the currently selected (or most recent) chunk. Monospace, scroll area, subtle row-number gutter.

4. **ClassificationTimeline component.** Vertical list of cards, newest on top. Each card:
   - Timestamp (relative, e.g. "3s ago").
   - Severity badge.
   - Confidence bar.
   - "Intended" severity (from the generator) vs "Predicted" severity (from the classifier). If they differ, show a small ⚠️ — useful to spot classifier mistakes during demo.
   - Click to expand → shows the actual log chunk in a collapsible region.

5. **SummaryStats component.** Small card at the top. Updates every tick. Computed from `history`.

6. **UX polish:**
   - When `running === false`, show a big dashed placeholder: "Press Start to begin the simulation".
   - Disable profile/interval controls while running (or allow live adjustment — your call; live adjustment is nicer).
   - Add a "Clear history" button.

7. **Commit:**
   ```bash
   git add .
   git commit -m "feat(phase-4): simulator page with synthetic log stream + live classification"
   ```

### Acceptance criteria
- Pressing Start with `profile:"mixed"` produces a mix of NORMAL/WARNING/ERROR chunks at the chosen interval.
- Pressing Stop halts new chunks without dropping the existing timeline.
- Setting `profile:"fatal"` produces mostly FATAL_OR_CRITICAL predictions (≥ 80%).
- Summary stats update in real time.
- The timeline visibly flags any "intended vs predicted" mismatches, which helps diagnose both classifier errors and template weaknesses.

### Gotchas
- **Don't forget to clear the `setInterval`** in the effect's cleanup function, or stopping the simulator won't actually stop it.
- **Don't use `setState` inside the interval callback without reading the latest state** — use the functional form (`setState(prev => ...)`) or `useRef` for anything that must stay fresh across ticks.
- **At high tick rates (1s interval)** a slow CPU classifier can fall behind. Either queue chunks, skip ticks while a request is in-flight (simpler), or clamp the minimum interval to 2s. Document this in the UI.
- **Time formatting:** use `Intl.RelativeTimeFormat` or `date-fns/formatDistanceToNow` — avoid `Date` math by hand.

---


## Phase 5 — ADK Agent System Foundation

### Goal
Stand up a minimal Google ADK project that exposes a single working agent via HTTP. No RAG, no reflection yet — this phase just verifies the plumbing: Gemini auth works, ADK loads the agent, the FastAPI app serves, and the frontend can reach it later.

### Prerequisites
- Phase 0 complete.
- A Gemini API key from [AI Studio](https://aistudio.google.com/apikey) (free tier is sufficient).

### Deliverables
- `rca-agent-system/` Python project with `google-adk` installed.
- A single `root_agent` exported from the `rca_system.agents` package.
- `server.py` that exposes the agent via `get_fast_api_app()` on :8000.
- `adk web` and `adk api_server` both work from the command line.
- End-to-end sanity check: `curl POST /run` returns a Gemini response.

### Tasks

1. **Create the Python project:**
   ```bash
   cd rca-agent-system
   uv init --python 3.11
   uv add google-adk google-genai
   uv add fastapi "uvicorn[standard]" sqlalchemy aiosqlite pydantic pydantic-settings python-dotenv
   uv add chromadb sentence-transformers    # needed in Phase 6; install now
   uv add --dev ruff pyright pytest
   ```

2. **Write `.env`** (from `.env.example`):
   ```bash
   GOOGLE_API_KEY=ya29.your-real-key
   GOOGLE_GENAI_USE_VERTEXAI=FALSE
   ADK_PORT=8000
   ADK_CORS_ORIGINS=http://localhost:3000
   CHROMA_PERSIST_DIR=./data/chroma
   CHROMA_COLLECTION=incident_memory
   SESSION_DB_URL=sqlite+aiosqlite:///./data/sessions.db
   GEMINI_MODEL=gemini-2.5-flash
   ```
   `GOOGLE_GENAI_USE_VERTEXAI=FALSE` tells ADK to use the public Gemini API (via API key), not Vertex AI. This is the zero-setup path. Flip to `TRUE` later if you want to move to Vertex AI.

3. **Directory structure:**
   ```bash
   mkdir -p rca_system/{agents,tools,memory} data/chroma seed/incidents scripts
   touch rca_system/__init__.py rca_system/agents/__init__.py rca_system/tools/__init__.py rca_system/memory/__init__.py
   ```

4. **Write `rca_system/settings.py`:**
   ```python
   from pydantic_settings import BaseSettings, SettingsConfigDict

   class Settings(BaseSettings):
       model_config = SettingsConfigDict(env_file=".env", extra="ignore")

       google_api_key: str
       google_genai_use_vertexai: str = "FALSE"
       adk_port: int = 8000
       adk_cors_origins: str = "http://localhost:3000"
       chroma_persist_dir: str = "./data/chroma"
       chroma_collection: str = "incident_memory"
       session_db_url: str = "sqlite+aiosqlite:///./data/sessions.db"
       gemini_model: str = "gemini-2.5-flash"

       @property
       def cors_origins_list(self) -> list[str]:
           return [o.strip() for o in self.adk_cors_origins.split(",") if o.strip()]

   settings = Settings()
   ```

5. **Write a placeholder `rca_system/agents/root_agent.py`** — a single LLM agent with no tools yet. This is a smoke test that Gemini auth works.
   ```python
   from google.adk.agents import Agent
   from rca_system.settings import settings

   root_agent = Agent(
       name="rca_root_agent",
       model=settings.gemini_model,
       description="Root orchestrator for root-cause analysis of software incidents.",
       instruction=(
           "You are an expert SRE assistant. When given a log chunk, briefly describe "
           "what you think is going wrong. In Phase 7 you'll be replaced by a multi-agent "
           "pipeline, but for now just return a one-paragraph diagnosis."
       ),
   )
   ```

6. **Expose it through the `agents` package:**
   ```python
   # rca_system/agents/__init__.py
   from .root_agent import root_agent

   __all__ = ["root_agent"]
   ```

7. **Make the agent package discoverable by ADK.** ADK's `get_fast_api_app(agents_dir=...)` looks for sub-directories each containing an `agent.py` or an `__init__.py` that exposes `root_agent`. The folder name becomes the `app_name` in the API.

   There are two layouts; we use the one that's friendliest to Python imports:

   **Layout A — ADK-native "agents directory":**
   ```
   rca-agent-system/
   ├── server.py
   └── rca_system/          ← this is the agent app name
       ├── __init__.py      ← exports root_agent
       └── agent.py         ← defines root_agent
   ```

   Under this layout, `agents_dir` passed to `get_fast_api_app` is the **parent** of `rca_system/`, i.e. the project root. The `app_name` visible via `/list-apps` will be `"rca_system"`.

   Adapt the layout we wrote in step 3 to match: put `root_agent` in `rca_system/agent.py` (with the code from step 5) and re-export from `rca_system/__init__.py`:
   ```python
   # rca_system/__init__.py
   from .agent import root_agent
   __all__ = ["root_agent"]
   ```

   The `rca_system/agents/` subfolder still exists — it's where we'll *implement* the individual sub-agents. The top-level `rca_system/agent.py` wires them together as `root_agent`. (Phase 7 does this wiring.)

8. **Write `server.py`:**
   ```python
   import os
   from pathlib import Path
   import uvicorn
   from fastapi import FastAPI
   from google.adk.cli.fast_api import get_fast_api_app
   from rca_system.settings import settings

   AGENTS_DIR = str(Path(__file__).parent.resolve())

   app: FastAPI = get_fast_api_app(
       agents_dir=AGENTS_DIR,
       session_service_uri=settings.session_db_url,
       allow_origins=settings.cors_origins_list,
       web=False,         # we're serving via our own frontend; set True during debugging
   )

   @app.get("/health")
   async def health():
       return {"status": "ok", "model": settings.gemini_model}

   if __name__ == "__main__":
       uvicorn.run(app, host="0.0.0.0", port=settings.adk_port)
   ```

9. **Create the sessions directory:**
   ```bash
   mkdir -p data
   ```

10. **Run it two ways:**

    **(a) Via `adk web`** — launches ADK's dev UI on :8000, with our agent available. Useful for local debugging.
    ```bash
    uv run adk web
    ```
    Open http://localhost:8000 → pick `rca_system` from the dropdown → chat with it. You should get Gemini responses.

    **(b) Via our `server.py`** — this is the deployment path.
    ```bash
    uv run python server.py
    ```
    Visit http://localhost:8000/docs — you should see all ADK's auto-generated endpoints plus our `/health`.

11. **End-to-end sanity check with curl:**
    ```bash
    # 1. Create a session
    curl -X POST http://localhost:8000/apps/rca_system/users/demo-user/sessions/test-sess-1 \
      -H "Content-Type: application/json" -d '{}'

    # 2. Run the agent
    curl -X POST http://localhost:8000/run \
      -H "Content-Type: application/json" \
      -d '{
        "app_name": "rca_system",
        "user_id": "demo-user",
        "session_id": "test-sess-1",
        "new_message": {"parts":[{"text":"Hello, can you hear me?"}], "role":"user"},
        "streaming": false
      }'
    ```
    Should return a JSON array of events ending with a Gemini-authored response.

12. **Commit:**
    ```bash
    git add .
    git commit -m "feat(phase-5): ADK agent system foundation with placeholder root agent"
    ```

### Acceptance criteria
- `adk web` and `python server.py` both start without errors.
- `curl GET /list-apps` returns `["rca_system"]`.
- Creating a session and running the agent returns a coherent Gemini response.
- `/health` returns `{status:"ok", model:"gemini-2.5-flash"}`.

### Gotchas
- **"Agent not found" error** → `agents_dir` probably points to the wrong folder. It should point to the parent directory that *contains* `rca_system/`, not `rca_system/` itself.
- **Module import errors** → the `rca_system/__init__.py` must export `root_agent`. ADK discovers agents by importing the package and looking for this symbol.
- **SQLite async driver** → use `sqlite+aiosqlite://`, not plain `sqlite://`. ADK's `DatabaseSessionService` requires the async driver.
- **Gemini rate limits** — the free tier has per-minute limits. If you see 429s during Phase 7 where agents chain multiple calls, add retry/backoff or upgrade the tier.
- **Model name typos** — `gemini-2.5-flash` is the current fast model as of this writing. If ADK errors with "model not found", check the current list in the Gemini API docs. `gemini-1.5-flash` is a safe fallback.

---

## Phase 6 — RAG Retrieval Agent + ChromaDB Knowledge Base

### Goal
Stand up the vector knowledge base, seed it with a starter set of incident documents, and build a retrieval agent that an LLM agent can call as a tool.

### Prerequisites
- Phase 5 complete.

### Deliverables
- `rca_system/memory/chroma_store.py` — a thin wrapper around ChromaDB's `PersistentClient` with add / query / update / delete methods that know about our custom metadata schema.
- `seed/incidents/*.md` — at least 6 starter incident documents covering common failure patterns.
- `scripts/seed_knowledge_base.py` — idempotent script that loads the markdown files into ChromaDB.
- `rca_system/tools/retrieve_incidents.py` — an ADK-callable function tool that does top-k similarity search and returns formatted results.
- A new `retrieval_agent` that exposes this tool (used as a sub-agent in Phase 7).

### Tasks

1. **Design the ChromaDB collection schema.**

   Each document in the collection represents one historical incident. Metadata fields:
   | Field | Type | Meaning |
   |---|---|---|
   | `incident_id` | string | stable unique id |
   | `title` | string | short human-readable title |
   | `severity` | string | `FATAL_OR_CRITICAL` / `ERROR` / `WARNING` |
   | `root_cause` | string | the verified root cause (short phrase) |
   | `resolution` | string | the fix that was applied |
   | `tags` | string | comma-separated tags (e.g. "redis,connection,network") |
   | `success_score` | float | starts at 1.0; reflection agent adjusts over time |
   | `usage_count` | int | how many times this entry has been retrieved |
   | `last_used_ts` | float | unix timestamp of last retrieval |
   | `added_ts` | float | unix timestamp of creation |

   The **document text** (what gets embedded) is a synthetic natural-language description built from title + root_cause + resolution + a representative log excerpt. This is what the embedding model sees.

2. **Write `rca_system/memory/chroma_store.py`:**
   ```python
   import time
   from dataclasses import dataclass, asdict
   from pathlib import Path
   import chromadb
   from chromadb.config import Settings as ChromaSettings
   from rca_system.settings import settings

   @dataclass
   class IncidentRecord:
       incident_id: str
       title: str
       severity: str
       root_cause: str
       resolution: str
       tags: str
       success_score: float = 1.0
       usage_count: int = 0
       last_used_ts: float = 0.0
       added_ts: float = 0.0

       def to_document(self) -> str:
           """Natural-language form used for embedding."""
           return (
               f"Title: {self.title}\n"
               f"Severity: {self.severity}\n"
               f"Root cause: {self.root_cause}\n"
               f"Resolution: {self.resolution}\n"
               f"Tags: {self.tags}"
           )


   class IncidentMemory:
       def __init__(self) -> None:
           Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
           self._client = chromadb.PersistentClient(
               path=settings.chroma_persist_dir,
               settings=ChromaSettings(anonymized_telemetry=False),
           )
           self._collection = self._client.get_or_create_collection(
               name=settings.chroma_collection,
               metadata={"hnsw:space": "cosine"},
           )

       def add(self, record: IncidentRecord, document_text: str | None = None) -> None:
           if record.added_ts == 0.0:
               record.added_ts = time.time()
           self._collection.upsert(
               ids=[record.incident_id],
               documents=[document_text or record.to_document()],
               metadatas=[asdict(record)],
           )

       def query(self, query_text: str, k: int = 5) -> list[dict]:
           res = self._collection.query(
               query_texts=[query_text],
               n_results=k,
               include=["metadatas", "documents", "distances"],
           )
           hits = []
           ids = res.get("ids", [[]])[0]
           metadatas = res.get("metadatas", [[]])[0]
           documents = res.get("documents", [[]])[0]
           distances = res.get("distances", [[]])[0]
           for i, m, d, dist in zip(ids, metadatas, documents, distances):
               hits.append({
                   "incident_id": i,
                   "document": d,
                   "metadata": m,
                   "distance": dist,               # cosine distance; lower = more similar
                   "similarity": 1 - dist,
               })
           return hits

       def update_score(self, incident_id: str, delta: float) -> None:
           """Adjust success_score by delta, clamped to [0.0, 2.0]."""
           res = self._collection.get(ids=[incident_id], include=["metadatas", "documents"])
           if not res["ids"]:
               return
           meta = res["metadatas"][0]
           new_score = max(0.0, min(2.0, meta.get("success_score", 1.0) + delta))
           meta["success_score"] = new_score
           self._collection.update(ids=[incident_id], metadatas=[meta])

       def mark_retrieved(self, incident_ids: list[str]) -> None:
           if not incident_ids:
               return
           res = self._collection.get(ids=incident_ids, include=["metadatas"])
           now = time.time()
           updated = []
           for meta in res["metadatas"]:
               meta["usage_count"] = int(meta.get("usage_count", 0)) + 1
               meta["last_used_ts"] = now
               updated.append(meta)
           self._collection.update(ids=res["ids"], metadatas=updated)

       def count(self) -> int:
           return self._collection.count()
   ```

   ChromaDB uses a default embedding function (`all-MiniLM-L6-v2`) if you don't specify one. That's fine for our prototype. If you want to swap it, configure `embedding_function=` on `get_or_create_collection`.

3. **Write starter seed documents** under `seed/incidents/`. See Appendix B for the full content of at least 6 starter incidents. Each file is plain Markdown with YAML frontmatter:

   ```markdown
   ---
   incident_id: redis-conn-refused-001
   title: Redis connection refused after network config change
   severity: ERROR
   root_cause: Firewall rule change blocked Redis port 6379 from app subnet
   resolution: Restored firewall rule; added alert for Redis connectivity
   tags: redis,network,connection,firewall
   ---

   Application failed to connect to Redis cache after a network maintenance window.
   Typical symptom: repeated `ECONNREFUSED` errors from the Redis client, followed
   by cache-miss cascades and elevated latency on read-heavy endpoints.

   ## Log excerpt
   ```
   ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused
   ERROR Retry failed: Connection refused
   ERROR Batch job #4521 failed: Cache unavailable
   ```
   ```

4. **Write `scripts/seed_knowledge_base.py`:**
   ```python
   """Seed (or reseed) ChromaDB from markdown files in seed/incidents/."""
   import re
   import yaml
   from pathlib import Path
   from rca_system.memory.chroma_store import IncidentMemory, IncidentRecord

   SEED_DIR = Path(__file__).parent.parent / "seed" / "incidents"

   def parse_markdown(path: Path) -> tuple[dict, str]:
       text = path.read_text()
       match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
       if not match:
           raise ValueError(f"Missing YAML frontmatter in {path}")
       meta = yaml.safe_load(match.group(1))
       body = match.group(2).strip()
       return meta, body

   def main() -> None:
       memory = IncidentMemory()
       n = 0
       for md in sorted(SEED_DIR.glob("*.md")):
           meta, body = parse_markdown(md)
           record = IncidentRecord(
               incident_id=meta["incident_id"],
               title=meta["title"],
               severity=meta["severity"],
               root_cause=meta["root_cause"],
               resolution=meta["resolution"],
               tags=meta["tags"],
           )
           # Embed both the structured summary AND the free-form body
           doc_text = record.to_document() + "\n\n" + body
           memory.add(record, document_text=doc_text)
           n += 1
       print(f"Seeded {n} incidents. Collection now has {memory.count()} entries.")

   if __name__ == "__main__":
       main()
   ```
   Add `pyyaml` to deps: `uv add pyyaml`.

   Run it:
   ```bash
   uv run python scripts/seed_knowledge_base.py
   ```

5. **Write `rca_system/tools/retrieve_incidents.py`** — an ADK **Function Tool**. ADK auto-converts annotated Python functions into tools; the docstring becomes the tool's description (which Gemini reads to decide when to call it).

   ```python
   from rca_system.memory.chroma_store import IncidentMemory

   _memory = IncidentMemory()

   def retrieve_incidents(query: str, k: int = 5) -> dict:
       """Retrieve up to `k` past incident records most similar to the given query.

       Args:
           query: Natural-language description of the current incident, or relevant
                  log excerpts. The more specific, the better the matches.
           k: Number of results to return (1-10). Defaults to 5.

       Returns:
           A dict with a single key `hits`, each element containing:
             - incident_id
             - title
             - severity
             - root_cause
             - resolution
             - similarity (0.0 - 1.0)
             - success_score (0.0 - 2.0; entries that have historically led to correct diagnoses score higher)
       """
       k = max(1, min(10, k))
       raw = _memory.query(query, k=k)
       _memory.mark_retrieved([h["incident_id"] for h in raw])

       hits = []
       for h in raw:
           m = h["metadata"]
           hits.append({
               "incident_id": h["incident_id"],
               "title": m["title"],
               "severity": m["severity"],
               "root_cause": m["root_cause"],
               "resolution": m["resolution"],
               "similarity": round(h["similarity"], 4),
               "success_score": round(m.get("success_score", 1.0), 3),
           })
       # Apply simple re-ranking: boost by success_score.
       hits.sort(key=lambda x: x["similarity"] * x["success_score"], reverse=True)
       return {"hits": hits}
   ```

   **Important:** the re-ranking step (`similarity * success_score`) is the first concrete instance of "dynamic memory." Entries that reflection has boosted will float above entries that have been demoted.

6. **Define the retrieval agent** — `rca_system/agents/retrieval_agent.py`:

   ```python
   from google.adk.agents import Agent
   from rca_system.settings import settings
   from rca_system.tools.retrieve_incidents import retrieve_incidents

   retrieval_agent = Agent(
       name="retrieval_agent",
       model=settings.gemini_model,
       description=(
           "Retrieves the most relevant past incidents from the knowledge base. "
           "Call this when the user describes a new incident and wants to find "
           "similar resolved cases."
       ),
       instruction=(
           "You are a retrieval specialist. Given a log chunk or incident description, "
           "formulate the most informative search query from it (focus on error messages, "
           "component names, symptom keywords) and call the `retrieve_incidents` tool. "
           "Present the results concisely as a numbered list with incident_id, title, "
           "severity, root_cause, similarity, and success_score. Do NOT fabricate incidents."
       ),
       tools=[retrieve_incidents],
   )
   ```

7. **Temporarily wire it into the root.** For quick end-to-end testing, point `rca_system/agent.py` at `retrieval_agent`:
   ```python
   from rca_system.agents.retrieval_agent import retrieval_agent
   root_agent = retrieval_agent
   ```
   (Phase 7 will replace this with the proper SequentialAgent orchestrator.)

8. **Manual test via `adk web`:**
   ```bash
   uv run adk web
   ```
   Ask it: _"We're seeing repeated `Connection refused` errors from our Redis client at 10.0.1.100:6379."_ — it should invoke `retrieve_incidents` and return the `redis-conn-refused-001` seed as the top hit.

9. **Commit:**
   ```bash
   git add .
   git commit -m "feat(phase-6): ChromaDB knowledge base + retrieval agent with dynamic re-ranking"
   ```

### Acceptance criteria
- `scripts/seed_knowledge_base.py` populates ChromaDB with ≥ 6 incidents idempotently (running it twice doesn't duplicate).
- `IncidentMemory().count()` returns the seed count.
- Calling `retrieve_incidents("Redis connection refused")` returns the `redis-conn-refused-001` record as the top hit with `similarity > 0.6`.
- Running the retrieval_agent via `adk web` shows a tool call to `retrieve_incidents` in the trace and a cleanly formatted numbered list response.
- `mark_retrieved` is called (verify by inspecting `usage_count` after a few runs via a direct ChromaDB query).

### Gotchas
- **First ChromaDB run downloads the embedding model** (~90 MB) → may take a minute on slow networks. This happens once, then cached.
- **ChromaDB's default metric** is L2, not cosine. We explicitly set `hnsw:space: cosine` so our `similarity = 1 - distance` arithmetic is valid.
- **Metadata values must be str/int/float/bool** — ChromaDB does not accept lists or dicts in metadata. We store `tags` as a comma-separated string for this reason.
- **The re-ranking multiplication can demote very-similar-but-noisy entries** — which is the whole point, but during early demos, entries all have `success_score == 1.0` so ranking effectively equals similarity ranking. Dynamic behavior shows up after Phase 7 runs.
- **Seed documents should be realistic.** The embedding quality is largely determined by how well your seed text matches the style of production log chunks. Use real-looking error messages.

---

## Phase 7 — Reasoning, Reflection & Memory-Update Agents

### Goal
Complete the multi-agent pipeline. Build the reasoning, reflection, and memory-update agents, and wire them together under a `SequentialAgent` as the new `root_agent`. After this phase, an incident sent to the agent system produces a full RCA: retrieval → hypothesis → self-critique → memory adjustment → final answer.

### Prerequisites
- Phase 6 complete.

### Deliverables
- `rca_system/agents/reasoning_agent.py`, `reflection_agent.py`, `memory_update_agent.py`.
- `rca_system/tools/record_reflection.py` — tool the reflection agent calls to persist its judgment.
- `rca_system/tools/update_memory.py` — tool the memory-update agent calls to apply score deltas and (optionally) add a new incident.
- `rca_system/agent.py` wires everything together as a `SequentialAgent` assigned to `root_agent`.
- `session.state` is used as the bus between agents — retrieval writes hits there, reasoning reads them, reflection reads reasoning's output, memory-update reads reflection's output.

### Tasks

1. **Understand the flow.** One RCA run is a sequential pipeline of four agents. Each agent reads from and writes to the ADK session state dictionary.

   ```
   user_message (log chunk)
      │
      ▼
   ┌───────────────────┐        writes: retrieved_hits
   │ retrieval_agent   │────────────────────────────────┐
   └───────────────────┘                                │
      │                                                 ▼
      ▼                                         session.state
   ┌───────────────────┐   reads: retrieved_hits
   │ reasoning_agent   │   writes: hypothesis, suggested_actions
   └───────────────────┘
      │
      ▼
   ┌───────────────────┐   reads: hypothesis + retrieved_hits
   │ reflection_agent  │   writes: reflection_verdict, reflection_scores
   └───────────────────┘
      │
      ▼
   ┌───────────────────┐   reads: reflection_scores
   │ memory_update_agt │   applies delta to each retrieved incident
   └───────────────────┘
      │
      ▼
   final consolidated answer to user
   ```

2. **Use `output_key`** — ADK agents can declare `output_key="foo"` which automatically stores their final text output in `session.state["foo"]`. This is the simplest way to chain agents.

3. **Rewrite `retrieval_agent` with `output_key`:**
   ```python
   retrieval_agent = Agent(
       name="retrieval_agent",
       model=settings.gemini_model,
       description="Retrieves past incidents similar to the current one.",
       instruction=(
           "Given the user's incident description or log chunk, call the `retrieve_incidents` "
           "tool with an informative query. Then summarize the results in a JSON object with "
           "a single key `hits`, which is a list of the tool's results verbatim. "
           "Return ONLY the JSON — no prose, no markdown fences."
       ),
       tools=[retrieve_incidents],
       output_key="retrieval_output",
   )
   ```

4. **Write `rca_system/agents/reasoning_agent.py`:**
   ```python
   from google.adk.agents import Agent
   from rca_system.settings import settings

   reasoning_agent = Agent(
       name="reasoning_agent",
       model=settings.gemini_model,
       description="Generates a root-cause hypothesis and suggested actions.",
       instruction=(
           "You are a senior SRE performing root-cause analysis.\n"
           "\n"
           "Inputs available:\n"
           "- The original log chunk (in the most recent user message).\n"
           "- Retrieval results: {retrieval_output}\n"
           "\n"
           "Produce a JSON object with these keys and nothing else:\n"
           "  hypothesis: A single paragraph describing the most likely root cause. "
           "    Explicitly note which retrieved incidents informed your reasoning (by incident_id).\n"
           "  confidence: A number in [0,1] reflecting your own confidence.\n"
           "  suggested_actions: A list of 2-4 concrete next steps for the on-call engineer.\n"
           "  evidence: A list of short quoted log lines or facts from retrieved incidents that "
           "    support the hypothesis.\n"
           "\n"
           "If the retrieval results look irrelevant to the current incident, say so honestly "
           "in the hypothesis field and set confidence below 0.5."
       ),
       output_key="reasoning_output",
   )
   ```

   Note the `{retrieval_output}` template placeholder — ADK substitutes `session.state["retrieval_output"]` at runtime. This is the official mechanism for passing structured data between sequential agents.

5. **Write `rca_system/tools/record_reflection.py`:**
   ```python
   def record_reflection(
       incident_score_deltas: dict[str, float],
       overall_quality: str,
       rationale: str,
   ) -> dict:
       """Persist the reflection agent's judgment about the current RCA run.

       Args:
           incident_score_deltas: Map of incident_id → score delta in [-0.2, +0.2].
               Positive means the incident was genuinely helpful; negative means it was
               noise or misleading.
           overall_quality: One of "high", "medium", "low" — reflection's verdict on
               the reasoning agent's hypothesis.
           rationale: Short paragraph explaining the verdict.

       Returns:
           A confirmation dict. This tool does not mutate memory directly; it just
           structures the reflection output for the memory-update agent to consume.
       """
       # Clamp deltas defensively
       clamped = {k: max(-0.2, min(0.2, float(v))) for k, v in incident_score_deltas.items()}
       return {
           "status": "recorded",
           "incident_score_deltas": clamped,
           "overall_quality": overall_quality,
           "rationale": rationale,
       }
   ```

6. **Write `rca_system/agents/reflection_agent.py`:**
   ```python
   from google.adk.agents import Agent
   from rca_system.settings import settings
   from rca_system.tools.record_reflection import record_reflection

   reflection_agent = Agent(
       name="reflection_agent",
       model=settings.gemini_model,
       description="Critiques the reasoning agent's hypothesis and scores each retrieved incident's usefulness.",
       instruction=(
           "You are a skeptical senior engineer reviewing a colleague's RCA.\n"
           "\n"
           "Inputs:\n"
           "- Original log chunk: in the user message.\n"
           "- Retrieval results: {retrieval_output}\n"
           "- Reasoning agent's hypothesis: {reasoning_output}\n"
           "\n"
           "For each retrieved incident, decide:\n"
           "  +0.1 to +0.2 if it was genuinely relevant and supported the hypothesis\n"
           "   0.0 if it was neutral (retrieved but not used in reasoning)\n"
           "  -0.1 to -0.2 if it was misleading or was incorrectly used\n"
           "\n"
           "Then rate the overall hypothesis quality as 'high', 'medium', or 'low' and "
           "explain why in 1-3 sentences.\n"
           "\n"
           "Finally, call the `record_reflection` tool with your judgments. "
           "Do not skip the tool call."
       ),
       tools=[record_reflection],
       output_key="reflection_output",
   )
   ```

7. **Write `rca_system/tools/update_memory.py`:**
   ```python
   from rca_system.memory.chroma_store import IncidentMemory

   _memory = IncidentMemory()

   def apply_reflection_to_memory(incident_score_deltas: dict[str, float]) -> dict:
       """Apply the reflection agent's score deltas to stored incidents.

       Args:
           incident_score_deltas: incident_id → delta, already clamped by the reflection tool.

       Returns:
           A dict mapping incident_id → {old_score, new_score}.
       """
       results = {}
       for iid, delta in incident_score_deltas.items():
           before = _memory._collection.get(ids=[iid], include=["metadatas"])
           if not before["ids"]:
               continue
           old = float(before["metadatas"][0].get("success_score", 1.0))
           _memory.update_score(iid, delta)
           after = _memory._collection.get(ids=[iid], include=["metadatas"])
           new = float(after["metadatas"][0].get("success_score", 1.0))
           results[iid] = {"old_score": round(old, 3), "new_score": round(new, 3), "delta": delta}
       return {"updated": results}
   ```

8. **Write `rca_system/agents/memory_update_agent.py`:**
   ```python
   from google.adk.agents import Agent
   from rca_system.settings import settings
   from rca_system.tools.update_memory import apply_reflection_to_memory

   memory_update_agent = Agent(
       name="memory_update_agent",
       model=settings.gemini_model,
       description="Applies reflection feedback to the knowledge base's success scores.",
       instruction=(
           "You receive the reflection output: {reflection_output}\n"
           "\n"
           "Extract the `incident_score_deltas` field and call the `apply_reflection_to_memory` "
           "tool with it. After the tool returns, produce a final consolidated RCA summary "
           "combining: the hypothesis from {reasoning_output}, the critique from "
           "{reflection_output}, and a one-line note about which incidents were boosted or "
           "demoted based on the tool's return value.\n"
           "\n"
           "Format the final summary as markdown with these sections:\n"
           "  ## Root cause\n"
           "  ## Suggested actions\n"
           "  ## Confidence & caveats\n"
           "  ## Memory updates\n"
       ),
       tools=[apply_reflection_to_memory],
       output_key="final_output",
   )
   ```

9. **Wire the pipeline** — rewrite `rca_system/agent.py`:
   ```python
   from google.adk.agents import SequentialAgent
   from rca_system.agents.retrieval_agent import retrieval_agent
   from rca_system.agents.reasoning_agent import reasoning_agent
   from rca_system.agents.reflection_agent import reflection_agent
   from rca_system.agents.memory_update_agent import memory_update_agent

   root_agent = SequentialAgent(
       name="rca_root_agent",
       description=(
           "Root-cause analysis pipeline for software incidents. "
           "Retrieves similar past incidents, generates a hypothesis, reflects on it, "
           "and updates memory based on the reflection."
       ),
       sub_agents=[
           retrieval_agent,
           reasoning_agent,
           reflection_agent,
           memory_update_agent,
       ],
   )
   ```

10. **Test end-to-end via `adk web`.** Send a message like:
    ```
    Investigate this log chunk:

    2024-01-15 16:30:01 ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused
    2024-01-15 16:30:02 INFO Retrying connection (attempt 1/3)
    2024-01-15 16:30:05 ERROR Retry failed: Connection refused
    2024-01-15 16:30:06 ERROR Batch job #4521 failed: Cache unavailable
    ```

    Expected behavior:
    - You see four agent invocations in the trace.
    - `retrieval_agent` calls `retrieve_incidents`, returns a JSON with `hits`.
    - `reasoning_agent` emits JSON with `hypothesis` pointing at the Redis incident.
    - `reflection_agent` calls `record_reflection` with a positive delta on `redis-conn-refused-001`.
    - `memory_update_agent` calls `apply_reflection_to_memory` and emits the final markdown summary.
    - Running a direct ChromaDB query afterwards shows that `redis-conn-refused-001`'s `success_score` is now > 1.0.

11. **Add a reset script** — `scripts/reset_memory.py`:
    ```python
    """Wipe ChromaDB and reseed — useful before a demo."""
    import shutil
    from pathlib import Path
    from rca_system.settings import settings
    import subprocess, sys

    p = Path(settings.chroma_persist_dir)
    if p.exists():
        shutil.rmtree(p)
        print(f"Removed {p}")
    subprocess.check_call([sys.executable, "scripts/seed_knowledge_base.py"])
    ```

12. **Commit:**
    ```bash
    git add .
    git commit -m "feat(phase-7): reasoning + reflection + memory-update agents; full RCA pipeline"
    ```

### Acceptance criteria
- Sending a Redis-connection-refused log chunk produces a final markdown summary with all four sections.
- The ADK trace in `adk web` clearly shows four agent turns.
- After a successful run, the `success_score` of the correctly-retrieved incident in ChromaDB has increased. After a run where reflection judged a retrieved incident as irrelevant, that incident's score has decreased.
- Re-running the same incident produces a **similar or better** hypothesis (because the relevant memory has been boosted).
- `scripts/reset_memory.py` cleanly restores initial state.

### Gotchas
- **Template placeholders in instructions:** `{retrieval_output}` is substituted from `session.state`. If a key is missing (e.g., the retrieval agent didn't actually call its tool and produced empty output), the placeholder will be empty and downstream agents will flail. Add defensive language in the reasoning agent's instruction: "If `{retrieval_output}` is empty, say so and proceed without retrieval context."
- **JSON robustness:** LLMs occasionally wrap JSON in markdown fences despite instructions. If the reasoning agent's output is consumed as structured data anywhere, parse defensively (strip ```json fences).
- **Sequential = blocking:** the whole pipeline runs serially. Total latency is typically 6-15s for 4 Gemini calls. That's fine for a demo but not for real-time production. We document this in the evaluation section.
- **Gemini free-tier rate limits** will bite during quick repeated tests. If you see 429s, add exponential backoff in ADK's callback hooks or upgrade to paid.
- **Tool calls are optional by default** — if an agent decides not to call its tool, the whole pipeline stalls. Use firm language like "Do not skip the tool call" in the reflection agent's instruction. ADK also supports forcing tool use via callbacks if the issue persists.


---

## Phase 8 — Frontend Pages for the Agent System

### Goal
Expose the agent system through the frontend: a manual `/agents` page for testing RCA with arbitrary log chunks, and a proper agent-timeline visualization component that can be reused in Phase 9's automation view.

### Prerequisites
- Phase 7 (agent system producing end-to-end output).
- Phase 3 (frontend already wired to a live backend).

### Deliverables
- `src/lib/api/agents.ts` — ADK client covering session creation + SSE consumption.
- `src/lib/hooks/useAgentStream.ts` — hook that exposes a streaming RCA run as reactive state.
- `src/components/agents/AgentTimeline.tsx` — the reusable timeline component.
- Working `/agents` page that accepts a log chunk and streams the RCA pipeline live.
- `/incidents` page that lists past sessions from ADK's session store.

### Tasks

1. **Add env var** to `frontend/.env.local`:
   ```
   NEXT_PUBLIC_AGENT_URL=http://localhost:8000
   ```

2. **Write the ADK client** — `src/lib/api/agents.ts`:
   ```ts
   import { v4 as uuidv4 } from "uuid";
   import type { AdkEvent } from "@/lib/types";

   const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL!;
   const APP_NAME = "rca_system";
   const USER_ID = "demo-user";

   export async function createSession(sessionId: string = uuidv4()): Promise<string> {
     const r = await fetch(
       `${AGENT_URL}/apps/${APP_NAME}/users/${USER_ID}/sessions/${sessionId}`,
       {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: "{}",
       },
     );
     if (!r.ok) throw new Error(`Failed to create session: ${r.status}`);
     return sessionId;
   }

   /**
    * Runs the agent and yields parsed ADK events as they stream in.
    * Uses fetch + a ReadableStream reader (NOT EventSource, because we need POST).
    */
   export async function* runAgentSSE(
     sessionId: string,
     userMessage: string,
     signal?: AbortSignal,
   ): AsyncGenerator<AdkEvent> {
     const response = await fetch(`${AGENT_URL}/run_sse`, {
       method: "POST",
       headers: { "Content-Type": "application/json" },
       signal,
       body: JSON.stringify({
         app_name: APP_NAME,
         user_id: USER_ID,
         session_id: sessionId,
         new_message: { parts: [{ text: userMessage }], role: "user" },
         streaming: true,
       }),
     });
     if (!response.ok || !response.body) {
       throw new Error(`Agent run failed: ${response.status}`);
     }

     const reader = response.body.getReader();
     const decoder = new TextDecoder();
     let buffer = "";

     while (true) {
       const { value, done } = await reader.read();
       if (done) break;
       buffer += decoder.decode(value, { stream: true });

       // SSE events are separated by \n\n; each data: line carries one JSON payload.
       const parts = buffer.split("\n\n");
       buffer = parts.pop() ?? "";
       for (const part of parts) {
         const line = part.split("\n").find((l) => l.startsWith("data:"));
         if (!line) continue;
         const payload = line.slice(5).trim();
         if (!payload) continue;
         try {
           yield JSON.parse(payload) as AdkEvent;
         } catch (err) {
           console.warn("Failed to parse SSE payload:", payload, err);
         }
       }
     }
   }

   export async function listSessions(): Promise<unknown[]> {
     const r = await fetch(`${AGENT_URL}/apps/${APP_NAME}/users/${USER_ID}/sessions`);
     if (!r.ok) return [];
     return r.json();
   }

   export async function getSession(sessionId: string): Promise<unknown> {
     const r = await fetch(
       `${AGENT_URL}/apps/${APP_NAME}/users/${USER_ID}/sessions/${sessionId}`,
     );
     if (!r.ok) throw new Error(`Session fetch failed: ${r.status}`);
     return r.json();
   }
   ```

   Install `uuid`: `pnpm add uuid @types/uuid`.

3. **Write the streaming hook** — `src/lib/hooks/useAgentStream.ts`:
   ```ts
   "use client";
   import { useCallback, useRef, useState } from "react";
   import { createSession, runAgentSSE } from "@/lib/api/agents";
   import type { AdkEvent } from "@/lib/types";

   export interface AgentRunState {
     status: "idle" | "streaming" | "done" | "error";
     sessionId: string | null;
     events: AdkEvent[];
     error: string | null;
   }

   export function useAgentStream() {
     const [state, setState] = useState<AgentRunState>({
       status: "idle",
       sessionId: null,
       events: [],
       error: null,
     });
     const abortRef = useRef<AbortController | null>(null);

     const run = useCallback(async (message: string) => {
       abortRef.current?.abort();
       const controller = new AbortController();
       abortRef.current = controller;

       setState({ status: "streaming", sessionId: null, events: [], error: null });
       try {
         const sessionId = await createSession();
         setState((s) => ({ ...s, sessionId }));
         for await (const ev of runAgentSSE(sessionId, message, controller.signal)) {
           setState((s) => ({ ...s, events: [...s.events, ev] }));
         }
         setState((s) => ({ ...s, status: "done" }));
       } catch (err) {
         if (controller.signal.aborted) {
           setState((s) => ({ ...s, status: "idle" }));
           return;
         }
         setState((s) => ({ ...s, status: "error", error: (err as Error).message }));
       }
     }, []);

     const cancel = useCallback(() => {
       abortRef.current?.abort();
     }, []);

     return { ...state, run, cancel };
   }
   ```

4. **Build `AgentTimeline` component** — the most important visual element. It takes `events: AdkEvent[]` and renders a vertical timeline with:
   - One "step" per distinct `event.author` (i.e., per sub-agent).
   - Each step shows:
     - Agent name as a header with an icon (`lucide-react`: `Search` for retrieval, `Brain` for reasoning, `Eye` for reflection, `Database` for memory-update, `Bot` for root).
     - Current status: "working" (pulsing dot), "done" (check), "error" (X).
     - Accumulated text output from that agent (streamed tokens concatenated).
     - Tool calls: render as collapsible cards showing tool name, arguments (JSON-highlighted), and response.
   - A final consolidated "Answer" card at the bottom that renders the last agent's markdown output using `react-markdown`.

   Install markdown deps: `pnpm add react-markdown remark-gfm`.

   The key logic: group `events` by `author`, accumulate `content.parts[*].text` per group in order.

5. **The `/agents` page:**
   - Two-column layout, similar to the classifier page.
   - Left: a Textarea for pasting a log chunk + a "Run RCA" button.
   - Below the button, an "Example incidents" dropdown with a few preset log chunks matching seeded incidents.
   - Right: the `AgentTimeline` consuming output from `useAgentStream`.
   - A "Cancel" button (visible while `status === "streaming"`) that calls `cancel()`.
   - On `status === "error"`, show an Alert with the error and a "Retry" button.

6. **The `/incidents` page:**
   - Fetch `listSessions()` on mount.
   - Render a table: session id, created at, last update, number of events.
   - Clicking a row navigates to `/incidents/[id]` (a detail page) that calls `getSession` and re-renders the saved events using the same `AgentTimeline` component. (This gives us "history replay" for free.)

7. **Nav:** update the sidebar to include `/incidents`. Replace the "Coming in Phase X" stub on `/agents`.

8. **Add a service-status pill** for the agent system in the top nav, similar to the classifier one. The `useAgentHealth` hook polls `/health`.

9. **Test thoroughly:**
   - Paste the Redis connection log → see four agent steps appear in sequence with streaming text → final markdown summary renders.
   - Cancel mid-run → stream stops, UI resets to idle.
   - Kill the agent service → health pill turns red → Run button shows a clear error.
   - Open `/incidents` → previous runs show up → clicking one replays the timeline.

10. **Commit:**
    ```bash
    git add .
    git commit -m "feat(phase-8): frontend pages for agent system (live streaming + history)"
    ```

### Acceptance criteria
- `/agents` shows the full pipeline streaming, with one section per sub-agent that fills in progressively.
- The final markdown summary renders with proper headings and formatting.
- Session history is browsable on `/incidents` and replayable.
- Both classifier and agent service status indicators show current health.
- No console errors during a full run.

### Gotchas
- **EventSource won't work here** — ADK's `/run_sse` requires POST with a JSON body; `EventSource` only does GET. Use `fetch` + `ReadableStream` reader as shown.
- **SSE event parsing:** some proxies (not a concern locally) buffer responses. If events don't arrive until the end, disable response buffering in the proxy or add `X-Accel-Buffering: no` if one is in the path.
- **Memory leak from abandoned streams:** always `abortController.abort()` when the user navigates away. Do this in a `useEffect` cleanup in the page.
- **Markdown XSS:** `react-markdown` is safe by default (no `dangerouslySetInnerHTML`), but don't bypass it.
- **Don't render `events.length` incrementally without keys** — React will warn. Use a stable key on each event (we have `event.id`).

---

## Phase 9 — End-to-End Automated Pipeline

### Goal
Fold the agent system into the simulator. When the classifier returns `should_invoke_rca: true` on a synthetic chunk, the UI automatically opens an SSE stream to the agent service and renders the full RCA inline with the classification timeline. This is the marquee demo of the project.

### Prerequisites
- Phase 4 (simulator with classifier loop).
- Phase 8 (agent streaming UI).

### Deliverables
- Updated `/simulator` page with a new "Automated RCA" column that:
  - Monitors the classification timeline.
  - When a new entry comes in with `should_invoke_rca: true`, automatically triggers an RCA run.
  - Renders an accordion-style list of "RCA investigations" in reverse-chronological order, each expandable to show the full agent timeline.
  - Displays summary badges per investigation: severity, time to complete, confidence, final root cause (extracted from the final markdown).
- Safeguards: cap concurrent RCA runs at 1 (queue the next trigger if one is in flight); allow the user to toggle "Auto-RCA" on and off.
- An end-to-end demo script in `docs/DEMO.md`.

### Tasks

1. **Extend the simulator state** to include an "investigations" array separate from "history":
   ```ts
   interface Investigation {
     id: string;                  // uuid matching session_id
     triggeredBy: string;         // id of the classification history entry that triggered this
     startedAt: number;
     completedAt: number | null;
     status: "queued" | "running" | "done" | "error";
     events: AdkEvent[];
     chunk: string;               // the original log chunk
     severity: Severity;
     finalAnswer: string | null;  // final markdown from memory_update_agent
   }
   ```

2. **Queue logic.** When a classification arrives with `should_invoke_rca: true`:
   - Push a new Investigation with status `"queued"`.
   - A separate `useEffect` watches the queue: if no investigation is `"running"` and there's at least one `"queued"`, start it.
   - Starting means: create an ADK session, begin SSE streaming, append events into the investigation's `events` array.
   - On stream completion, extract the final markdown and set `finalAnswer`, `completedAt`, and status `"done"`.

   Important: **don't parallelize RCA runs**. Gemini rate limits, ADK session ordering, and the ChromaDB memory state are simpler with one run at a time. Queued items just wait.

3. **Investigations UI.** A new column (or a switch between "Classifications" and "Investigations" tabs — either is fine). Each investigation renders as:
   - A header row: severity badge, "triggered at" relative time, "completed in N.Ns" (or "running..."), an expand/collapse chevron.
   - Collapsed: show only the root-cause line (first ~80 chars of the "Root cause" section of `finalAnswer`).
   - Expanded: show the full `AgentTimeline` (reuse the Phase 8 component) and the complete final markdown.

4. **Auto-RCA toggle.** Add a switch in the simulator controls panel. When off, classification still runs but no RCA is triggered. The queue is cleared when the toggle flips off (document this behavior in the UI — "Turning off auto-RCA cancels any pending investigations").

5. **Investigation lifecycle callouts.**
   - When an investigation starts, briefly highlight the corresponding classification timeline entry with a left-border accent.
   - When it completes, show a small toast (use `sonner` or shadcn's toast) — "Incident analyzed: Redis connection refused".

6. **Extract root cause heuristic** — since the final markdown has a known structure (`## Root cause` section), extract the line immediately after it:
   ```ts
   function extractRootCause(markdown: string): string {
     const match = markdown.match(/##\s*Root cause\s*\n([^\n#]+)/i);
     return match ? match[1].trim() : "(unable to parse root cause)";
   }
   ```

7. **Polish the demo flow:**
   - Set the default profile to `"mixed"` and interval to 3s — this gives a natural cadence where an RCA fires every ~20s.
   - Add a "Quick demo mode" button that preloads the simulator with a specific sequence: two normals, one error, one normal, one fatal. This guarantees the demo shows both the gating behavior and multiple RCA runs.
   - Add a "Reset demo" button that: stops the simulator, clears history + investigations, and optionally calls a dedicated `/reset` endpoint on the agent service (see next step).

8. **Optional: `/reset` endpoint on the agent service** — a custom route added to `server.py` (not an ADK-generated one) that wipes ChromaDB and reseeds it. Gated behind an env-var feature flag so it's obviously not for production.
   ```python
   # server.py (inside if os.getenv("ALLOW_DEMO_RESET") == "1":)
   from rca_system.memory.chroma_store import IncidentMemory
   import shutil
   from pathlib import Path

   @app.post("/demo/reset-memory")
   async def reset_memory():
       from rca_system.settings import settings
       p = Path(settings.chroma_persist_dir)
       if p.exists():
           shutil.rmtree(p)
       # Reimport to recreate + reseed
       import subprocess, sys
       subprocess.check_call([sys.executable, "scripts/seed_knowledge_base.py"])
       return {"status": "ok", "count": IncidentMemory().count()}
   ```

9. **Write `docs/DEMO.md`** — a runbook for showing the project:
   - Start order: `classifier-service` → `rca-agent-system` → `frontend`.
   - Open `/simulator`.
   - Click "Quick demo mode".
   - Narrate: "NORMAL and WARNING chunks are classified cheaply in milliseconds — RCA is not triggered. When ERROR appears, the classifier flags it, a session is created, and the four-agent pipeline runs."
   - Open `/incidents` to show history.
   - Open `/agents` to show manual single-shot mode.

10. **Commit:**
    ```bash
    git add .
    git commit -m "feat(phase-9): end-to-end automated pipeline in the simulator"
    ```

### Acceptance criteria
- Running the simulator with `profile:"mixed"` for 2 minutes produces at least one completed RCA investigation visible in the Investigations column.
- Toggling Auto-RCA off stops new investigations from starting; classifications continue.
- Queued investigations start sequentially, never concurrently.
- Final root-cause line is correctly extracted and shown in the collapsed investigation header.
- Navigation between `/simulator`, `/agents`, `/incidents` without losing state.

### Gotchas
- **State drift after hot-reload in dev:** the investigations queue can stall if Next.js hot-reloads the simulator page while an SSE stream is open. Guard with `useEffect` cleanup that aborts active streams.
- **Clock skew:** timestamps inside ADK events come from the server. Don't mix them with browser `Date.now()` when computing durations — always use one clock consistently (pick event timestamps, convert at display time).
- **Memory grows unbounded** if the simulator runs for hours — cap `events.length` per investigation at, say, 500, and cap `investigations.length` at 30, dropping oldest. Real demos don't run that long but students *will* leave it running overnight.
- **Gemini free tier:** at 3s tick + ~1/20 fire rate, you're firing ~9 RCAs/hour, ~36 Gemini calls/hour. That's within free tier limits but leaves no headroom for repeated demos. Consider pre-filling the memory with several runs before a presentation so you're not showing cold-start latency.

---

## Phase 10 — Polish, Evaluation & Demo Prep

### Goal
Ship-ready: the system runs reliably, is easy to start, has basic evaluation numbers for the thesis, and looks good for examiners.

### Prerequisites
- Phases 0–9 complete and working.

### Deliverables
- Evaluation scripts and results tables.
- Top-level `make`-style task runner (`justfile` or bash scripts) so "run everything" is one command.
- Optional `docker-compose.yml`.
- Clean READMEs per sub-project.
- Screenshots directory + GIF of the automation loop for the thesis.
- Final checklist of research-question coverage.

### Tasks

1. **Evaluation scripts** — create `rca-agent-system/scripts/evaluate.py`:
   - Load a small held-out set of 10-20 incident scenarios (authored by hand — one log chunk + ground-truth root cause per scenario).
   - For each, run the full RCA pipeline.
   - Compare the extracted "Root cause" text against ground truth. Use:
     - **Keyword overlap** — simple: does the root-cause string contain the ground-truth keywords?
     - **LLM-as-judge** — more robust: a separate Gemini call asking "is hypothesis H consistent with ground truth G?" yielding yes/no/partial.
   - Aggregate to: accuracy (exact/partial/miss), mean time-to-hypothesis, mean retrieval similarity of the top hit.

2. **Memory-evolution evaluation** — show the dynamic memory actually works:
   - Run the same 10 incidents twice in sequence.
   - Record the final `success_score` of each seed incident after run 1 and after run 2.
   - Expect: incidents retrieved for *correct* diagnoses have `success_score > 1.0`; incidents retrieved but marked irrelevant have `success_score < 1.0`.
   - This is **a key novelty claim** of the project — produce a chart or table showing it for the thesis.

3. **Evaluation dataset** — `rca-agent-system/eval/incidents.jsonl`:
   ```json
   {"log_chunk": "...", "ground_truth_root_cause": "Redis connection refused due to firewall change", "expected_incident_id": "redis-conn-refused-001"}
   ```
   Write at least 15 of these. Cover each seeded incident category + a few "out-of-distribution" cases (where the system should honestly say "I don't have a close match").

4. **Task runner.** Add a `Justfile` (or `Makefile`) at repo root:
   ```just
   # Install all dependencies
   install:
       cd frontend && pnpm install
       cd classifier-service && uv sync
       cd rca-agent-system && uv sync

   # Seed the knowledge base (idempotent)
   seed:
       cd rca-agent-system && uv run python scripts/seed_knowledge_base.py

   # Run all three services concurrently (requires `concurrently` or `tmux`)
   dev:
       concurrently \
         "cd classifier-service && uv run uvicorn app.main:app --port 8001 --reload" \
         "cd rca-agent-system && uv run python server.py" \
         "cd frontend && pnpm dev"

   # Clean & reseed memory for fresh demo
   reset-demo:
       cd rca-agent-system && uv run python scripts/reset_memory.py

   # Run the evaluation suite
   eval:
       cd rca-agent-system && uv run python scripts/evaluate.py
   ```

5. **Dockerfiles (optional but nice).** Per-service Dockerfiles + a `docker-compose.yml`. Keep models outside the image (mount as volumes) to keep images small. Skip if time-constrained — the thesis doesn't require containerization.

6. **READMEs.** Each sub-project needs its own `README.md` covering:
   - What it does.
   - Prerequisites.
   - Install commands.
   - Run commands.
   - Env vars.
   - Troubleshooting for the 2-3 most likely problems.
   Monorepo README is a short pointer to each sub-project and to this guide.

7. **Screenshots & GIF.** Take screenshots of: classifier page with a prediction, simulator in automation mode mid-RCA, agents page with expanded timeline, incidents history. Record a 30-60s GIF of the full automation loop (use `ScreenToGif` on Windows, `Kap` on macOS, `peek` on Linux). Place in `docs/screenshots/`.

8. **Research-question coverage audit.** Before submission, verify each RQ/RO from the proposal has concrete evidence in the implementation:

   | Ref | How the implementation answers it |
   |---|---|
   | **RQ1 / RO1** How can reflective feedback evaluate retrieval? | Reflection agent scores each retrieved incident (-0.2 to +0.2); evidence in `reflection_agent.py` + eval results. |
   | **RQ2 / RO3** Multi-agent architecture for retrieval / reflection / memory? | `SequentialAgent` pipeline in `rca_system/agent.py`; four specialized sub-agents with clear responsibilities. |
   | **RQ3 / RO4** Dynamic memory updates over time? | `IncidentMemory.update_score`, re-ranking via `similarity * success_score`, demonstrated in Phase 10 memory-evolution eval. |
   | **RQ4 / RO5** Effectiveness vs manual investigation? | Time-to-hypothesis and accuracy metrics from evaluation; classifier gating demonstrates NORMAL chunks avoid expensive calls. |
   | **RO2** Feedback loop refining reasoning? | `retrieval_output → reasoning_output → reflection_output → memory mutation → next retrieval is re-ranked`: a visible closed loop across runs. |

9. **Final commit & tag:**
   ```bash
   git add .
   git commit -m "docs(phase-10): polish, evaluation, demo prep"
   git tag v1.0-thesis-submission
   ```

### Acceptance criteria
- `just install` works on a fresh machine (no missing deps).
- `just dev` starts all three services without manual intervention.
- `just eval` produces a JSON + markdown report with accuracy, latency, memory-evolution figures.
- Each sub-project's README lets a new developer run it in < 5 minutes.
- At least one clear screenshot per major UI area exists.
- All research questions have a traceable answer in the codebase + evaluation.

### Gotchas
- **LLM-as-judge is flaky.** Run the evaluation 3 times and average — single runs are noisy.
- **Don't demo on a cold system.** Warm up the classifier model and pre-seed one or two successful RCAs into memory before a presentation so you're not showing cold-start awkwardness on stage.
- **Free-tier Gemini can be slow during peak hours.** If a live demo is on a schedule, upgrade briefly or pre-run the critical traces.
- **Leave `ALLOW_DEMO_RESET` off** unless you want an examiner to accidentally wipe state.

---

## Appendix A — Synthetic Log Templates

These templates live in `classifier-service/app/log_generator.py` and are served via `POST /generate-logs`. Each template is a list of line-generator functions. The service picks lines from the matching profile's pool and intersperses timestamps.

The profiles:

### `normal`
Lines: routine INFO / DEBUG messages about request handling, healthchecks, periodic jobs. No anomaly keywords. Expected classifier output: `NORMAL`.

Sample lines:
```
INFO  HTTP 200 GET /api/health (12ms)
INFO  Processing scheduled job #{n}: daily-rollup
INFO  Cache hit ratio: 94.3%
DEBUG Connection pool: 12/50 active
INFO  Backup completed in 6.1s
```

### `warning`
Lines: elevated latency, retries, deprecation warnings, queue-depth alerts. No outright failures. Expected: `WARNING`.

Sample lines:
```
WARN  Request latency elevated: p99={lat}ms (threshold 500ms)
WARN  Deprecated endpoint /v1/users — migrate to /v2/users
WARN  Queue depth: {depth} (capacity 10000)
WARN  Retry attempt 2/3 for upstream service 'payments'
WARN  Certificate expires in {days} days
```

### `error`
Lines: application errors, failed requests, 5xx responses, DB connection failures, cache unavailability. Some INFO context lines interspersed. Expected: `ERROR`.

Sample lines:
```
ERROR HTTP 500 POST /api/orders — IntegrityError: duplicate key
ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused
ERROR Upstream 'inventory' timed out after 30s
ERROR Exception in thread 'worker-{n}': NullPointerException at OrderService.process(OrderService.java:142)
ERROR Queue consumer lag: {lag}s — SLO breached
```

### `fatal`
Lines: process crashes, OOM, unrecoverable errors, core dumps, cascading service failures. Expected: `FATAL_OR_CRITICAL`.

Sample lines:
```
FATAL Out of memory: Java heap space — Cannot allocate {mb}MB
FATAL JVM terminated. Core dump written to /var/crash/core.{pid}
FATAL Service '{svc}' crashed. PID {pid} exited with signal 9
FATAL Unrecoverable database corruption detected in tablespace 'prod_orders'
ERROR Cascading failure: {n} dependent services unreachable
```

### `mixed` (default for the automation demo)
Picks a profile per chunk via weighted random: `NORMAL 70%, WARNING 15%, ERROR 12%, FATAL 3%`.

### Generator implementation sketch

```python
import random
from datetime import datetime, timedelta

NORMAL_LINES = [
    lambda t, r: f"{t} INFO  HTTP 200 GET /api/health ({r.randint(8,40)}ms)",
    lambda t, r: f"{t} INFO  Processing scheduled job #{r.randint(1000,9999)}: daily-rollup",
    lambda t, r: f"{t} INFO  Cache hit ratio: {r.uniform(85, 99):.1f}%",
    lambda t, r: f"{t} DEBUG Connection pool: {r.randint(5, 40)}/50 active",
    lambda t, r: f"{t} INFO  Backup completed in {r.uniform(3, 12):.1f}s",
]
# ... similar lists for WARNING_LINES, ERROR_LINES, FATAL_LINES, plus a few
# INFO "context" lines usable in error/fatal chunks for realism.

PROFILES = {
    "normal":  {"primary": NORMAL_LINES, "secondary": [], "primary_ratio": 1.0,  "severity": "NORMAL"},
    "warning": {"primary": WARNING_LINES, "secondary": NORMAL_LINES, "primary_ratio": 0.3, "severity": "WARNING"},
    "error":   {"primary": ERROR_LINES,   "secondary": NORMAL_LINES, "primary_ratio": 0.4, "severity": "ERROR"},
    "fatal":   {"primary": FATAL_LINES,   "secondary": ERROR_LINES + NORMAL_LINES, "primary_ratio": 0.3, "severity": "FATAL_OR_CRITICAL"},
}

MIXED_WEIGHTS = [("normal", 70), ("warning", 15), ("error", 12), ("fatal", 3)]

def generate_log_chunk(profile: str, num_lines: int = 30, seed: int | None = None) -> tuple[str, str]:
    r = random.Random(seed)
    if profile == "mixed":
        profile = r.choices([p for p,_ in MIXED_WEIGHTS], weights=[w for _,w in MIXED_WEIGHTS], k=1)[0]
    cfg = PROFILES[profile]

    t = datetime.utcnow()
    lines = []
    for i in range(num_lines):
        t += timedelta(seconds=r.randint(1, 4))
        ts = t.strftime("%Y-%m-%d %H:%M:%S")
        pool = cfg["primary"] if r.random() < cfg["primary_ratio"] or not cfg["secondary"] else cfg["secondary"]
        lines.append(r.choice(pool)(ts, r))
    return "\n".join(lines), cfg["severity"]
```

Feel free to expand the line pools — the richer the templates, the more interesting the demo. Aim for at least 10 line generators per profile.

---

## Appendix B — Initial Knowledge Base Seed Documents

These files go in `rca-agent-system/seed/incidents/`. Write at least 6. The quality of retrieval depends heavily on how representative these are.

### B.1 `redis_connection_refused.md`
```markdown
---
incident_id: redis-conn-refused-001
title: Redis connection refused after network config change
severity: ERROR
root_cause: Firewall rule change blocked Redis port 6379 from the app subnet
resolution: Restored the firewall rule; added a monitoring probe specifically for Redis connectivity
tags: redis,network,connection,firewall,cache
---

Application hosts in the app subnet lost the ability to reach the Redis cluster at
10.0.1.100:6379 after a network team maintenance window. Symptoms: every batch
job that touched Redis failed within seconds of starting; cache-miss cascades
caused elevated read latency on the API. Recovery was manual restoration of the
previously-allowed firewall rule by the networking team.

## Log excerpt
ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused
ERROR Retry failed: Connection refused
ERROR Batch job #4521 failed: Cache unavailable

## What worked
- Correlated the start of errors with the network team's change ticket.
- Verified with `nc -zv 10.0.1.100 6379` from an app host (refused).

## What did NOT help
- Restarting the app process (the problem was external).
- Scaling the cache cluster (it was reachable from its own subnet).
```

### B.2 `jvm_oom.md`
```markdown
---
incident_id: jvm-oom-heap-001
title: Order processor JVM OOM on heap exhaustion
severity: FATAL_OR_CRITICAL
root_cause: Heap size too small for peak daily volume; unbounded LRU cache growth
resolution: Increased -Xmx from 512m to 2g; added size cap to the internal order-history cache
tags: jvm,java,oom,heap,memory,order-processor
---

The order-processor service crashed with OutOfMemoryError during a peak period.
Java flight recorder showed the internal order-history cache occupying ~80% of
heap just before the crash. The cache was implemented as a LinkedHashMap
without a size limit. Fix was a two-part change: raise heap size and cap the
cache at 10k entries using a proper LRU eviction policy.

## Log excerpt
FATAL Out of memory: Java heap space - Cannot allocate 512MB
FATAL JVM terminated. Core dump written to /var/crash/core.4521
FATAL Service 'order-processor' crashed. PID 4521 exited with signal 9
ERROR Cascading failure: 3 dependent services unreachable
```

### B.3 `db_deadlock.md`
```markdown
---
incident_id: db-deadlock-001
title: Frequent DB deadlocks on concurrent order updates
severity: ERROR
root_cause: Two code paths acquired row locks in opposite order under contention
resolution: Refactored both paths to acquire locks in a canonical order (orders then order_items)
tags: database,postgres,deadlock,transaction,concurrency
---

Under high concurrency the orders-service saw repeated deadlock errors from
PostgreSQL. Two transactional code paths — "update order total" and "add order
item" — were each acquiring row locks on the `orders` and `order_items` tables
but in opposite orders. Under contention this produced classic deadlocks.

## Log excerpt
ERROR SQLSTATE[40P01]: Deadlock detected
ERROR Transaction rolled back: deadlock detected (txn_id=84771)
ERROR Retry attempt 3/3 failed on order update path

## Remediation
- Standardized lock ordering: always acquire `orders` row first, then `order_items`.
- Added a DB-level monitoring alert for pg_stat_database.deadlocks.
```

### B.4 `upstream_timeout.md`
```markdown
---
incident_id: upstream-timeout-payments-001
title: Payments upstream timeouts during promotional event
severity: ERROR
root_cause: Payments service was under-scaled for the promotional event traffic
resolution: Coordinated a capacity plan with the payments team before major events; added circuit-breaker fallback
tags: upstream,timeout,circuit-breaker,payments,capacity
---

During a flash sale, the payments service started timing out after 30s on a
significant fraction of requests. Our orders service had no circuit breaker, so
the timeouts cascaded into user-visible errors. Root cause was the payments
team hadn't been notified of the sale and hadn't scaled; aggravated by our
missing circuit breaker.

## Log excerpt
ERROR Upstream 'payments' timed out after 30s
ERROR Order #8291 failed at payment step
WARN  Circuit breaker open (fallback active) — 18 consecutive failures
```

### B.5 `cert_expired.md`
```markdown
---
incident_id: tls-cert-expired-001
title: TLS certificate expired on internal API
severity: FATAL_OR_CRITICAL
root_cause: Auto-renewal cron job had stopped running after a host migration
resolution: Migrated cert renewal to the central automation platform; added expiry alerts 30/14/7 days out
tags: tls,certificate,expiry,automation,internal-api
---

The internal admin API became unreachable at midnight. All clients hit
`certificate_verify_failed`. The certificate was expired. Investigation found
the cron job that ran `certbot renew` had been tied to a specific host that was
decommissioned 60 days prior, and nobody noticed because there were no
near-expiry alerts.

## Log excerpt
ERROR HTTPS handshake failed: certificate verify failed (expired)
ERROR admin-api health-check failed (connect: error)
FATAL Maintenance dashboard unreachable — deploy blocked
```

### B.6 `disk_full.md`
```markdown
---
incident_id: disk-full-log-001
title: Disk full on app host caused service to hang
severity: FATAL_OR_CRITICAL
root_cause: Application log files not rotated; /var/log filled to 100%
resolution: Installed logrotate config; added a Prometheus alert at 85% disk usage
tags: disk,log-rotation,filesystem,logrotate,monitoring
---

The app service became unresponsive. `df -h` revealed /var/log at 100%. The
service was configured to write verbose logs but logrotate wasn't configured on
this host (it was a recently-provisioned VM). Once the disk filled, log writes
blocked, which stalled the service.

## Log excerpt
ERROR Failed to write to log file: no space left on device
FATAL Service stuck: unable to flush buffers
WARN  Disk usage: 100% /var/log (prior alert threshold was 95%)
```

### B.7+ additional suggestions
Add a few more to round out coverage: DNS resolution failure, misconfigured feature flag causing 100% error rate, memory leak in Python worker, Kubernetes pod OOMKilled, rate-limited by external API. You want ~8-12 seeds minimum for interesting retrieval behavior.

---

## Appendix C — Glossary

| Term | Meaning |
|---|---|
| **ADK** | Google Agent Development Kit. Python framework for building multi-agent LLM systems. |
| **Agent** | In ADK: a unit of LLM-driven behavior with an instruction, a model, and optional tools. |
| **AgentTool** | Pattern where one agent wraps another as a callable tool. Useful when the orchestrator should decide dynamically whether to delegate. |
| **Chunk** | A fixed-size window of consecutive log lines passed to the classifier. Currently 30 lines (~2 min). |
| **Dynamic memory** | Knowledge base that updates weights/entries based on feedback. Here: ChromaDB plus `success_score` re-ranking. |
| **Event** (ADK) | One message in an agent run — can be a user message, a model reply, a tool call, or a tool response. |
| **get_fast_api_app** | ADK helper that builds a FastAPI app exposing agents as HTTP endpoints. |
| **ModernBERT** | A modern BERT-family encoder with 8192-token context. Used here as the log severity classifier. |
| **RAG** | Retrieval-Augmented Generation. Fetch relevant documents first, pass them to the LLM, then generate. |
| **RCA** | Root-Cause Analysis. Going beyond symptoms to find the underlying reason a failure happened. |
| **Reflection** | An agent evaluating its own or a peer's output, typically to score quality or flag errors. |
| **SequentialAgent** | ADK workflow agent that runs sub-agents in a fixed order, passing session state between them. |
| **Session** | ADK's per-conversation context, holding history and shared state accessible via `session.state`. |
| **Severity** | One of `FATAL_OR_CRITICAL`, `ERROR`, `WARNING`, `NORMAL`. Classifier output. |
| **should_invoke_rca** | Boolean: `true` iff severity ∈ {FATAL_OR_CRITICAL, ERROR}. Drives the automation gate. |
| **SSE** | Server-Sent Events. One-way HTTP streaming. ADK uses this for `/run_sse`. |
| **success_score** | Per-incident float (0.0 to 2.0, default 1.0) in ChromaDB metadata. Reflection agent adjusts it; retrieval ranks on `similarity * success_score`. |

---

## Final Notes for Implementing Agents

If you're an AI coding agent reading this, here's how to get the best results:

1. **Execute one phase at a time.** Don't try to scaffold all 10 phases at once. Each phase has acceptance criteria — verify before moving on.

2. **When you're unsure, re-read §6 (Global Conventions) and §7 (API & Data Contracts).** Those are the load-bearing sections. Everything else is shape and polish.

3. **The code snippets in this guide are illustrative, not canonical.** Adapt them to the latest API shapes of the libraries you use. If a snippet contradicts a library's current docs, the library docs win — but please preserve the *contract* (function name, argument types, return shape) so other pieces keep working.

4. **Ask the user before:**
   - Adding a new cross-project dependency.
   - Changing any of the contracts in §7.
   - Renaming directories from §5.
   - Switching away from Gemini, ChromaDB, shadcn, or Next.js App Router.

5. **Assume the user is a final-year software engineering student.** Explain non-trivial choices in code comments and commit messages. Prefer readable code over cleverness. The thesis grade depends on the code being understandable by examiners.

---

*End of implementation guide.*
