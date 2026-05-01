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

```bash
cd rca-agent-system
uv sync                          # or: pip install -e .
cp .env.example .env             # set GOOGLE_API_KEY
python scripts/seed_knowledge_base.py
adk web                          # or: uvicorn rca_system.server:app --port 8000
```
