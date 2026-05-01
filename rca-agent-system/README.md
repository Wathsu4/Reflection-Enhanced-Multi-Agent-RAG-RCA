# rca-agent-system

Google ADK multi-agent system that performs root-cause analysis on log
chunks flagged by `classifier-service`. Built around a `SequentialAgent`
that orchestrates retrieval, reasoning, reflection, and memory-update
sub-agents over a ChromaDB knowledge base.

Status: **scaffold only** (Phase 0). Implementation lands in Phases 5-7
of [`PROJECT_IMPLEMENTATION_GUIDE.md`](../PROJECT_IMPLEMENTATION_GUIDE.md).

## Layout (planned)

```
rca-agent-system/
├── pyproject.toml
├── .env.example
├── seed/incidents/        # markdown KB documents (Phase 6 seeds these)
├── data/                  # ChromaDB + sessions.db (gitignored, runtime)
├── scripts/
│   ├── seed_knowledge_base.py
│   └── reset_memory.py
└── rca_system/            # importable package
    ├── server.py          # FastAPI app via ADK's get_fast_api_app()
    ├── settings.py
    ├── memory/            # ChromaDB wrapper + dynamic relevance scoring
    ├── tools/             # retrieve / update_memory / record_reflection
    └── agents/            # root_agent + sub-agents
```

Default port: `8000` (ADK convention).

## Quick start (once implemented)

**Mac / Linux**

```bash
cd rca-agent-system
uv sync --extra dev
cp .env.example .env             # then edit to set GOOGLE_API_KEY
uv run python scripts/seed_knowledge_base.py
uv run adk web                   # or: uv run python server.py
```

**Windows (PowerShell)**

```powershell
cd rca-agent-system
uv sync --extra dev
Copy-Item .env.example .env      # then edit to set GOOGLE_API_KEY
uv run python scripts\seed_knowledge_base.py
uv run adk web                   # or: uv run python server.py
```

`uv` works identically on all platforms; only the `cp`/`Copy-Item` and path
separators differ. If you don't have `uv`, replace `uv run` with activating
a venv first (`source .venv/bin/activate` on Mac/Linux,
`.\.venv\Scripts\Activate.ps1` on Windows).
