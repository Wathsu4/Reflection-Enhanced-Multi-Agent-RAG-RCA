# Demo runbook

A 5-minute walkthrough of the full system. Use this to rehearse the
thesis presentation or to onboard someone to the project.

## Prerequisites

- A real Gemini API key in `rca-agent-system/.env` (see
  `rca-agent-system/.env.example`).
- The classifier model available locally — see `classifier-service/README.md`.
- Node 20+, pnpm 9+, Python 3.14+, uv.

## Start order

The frontend depends on both backends being healthy, so bring them up
in this order. Each command runs in its own terminal.

### 1. classifier-service (port 8001)

```bash
cd classifier-service
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Wait for `Model loaded on device=...` in the log. The first run may
download the ModernBERT weights (~300 MB).

### 2. rca-agent-system (port 8000)

```bash
cd rca-agent-system
# One-time setup (or after `git pull` that touched seed/incidents/):
uv run python scripts/seed_knowledge_base.py

# To enable the demo reset endpoint (recommended for live demos):
ALLOW_DEMO_RESET=1 uv run python server.py
# Or, in production, just:
# uv run python server.py
```

Wait for `Application startup complete.` and `Uvicorn running on
http://0.0.0.0:8000`.

### 3. frontend (port 3000)

```bash
cd frontend
pnpm install   # only if dependencies have changed
pnpm dev
```

Open `http://localhost:3000` once it says `Ready in ...`. Both pills
in the top nav should turn green within 10s — the green Classifier and
Agent pills confirm the two backends are up.

## Demo script (~5 minutes)

### Act 1: Manual classification (~30s)

1. Click **Classify & RCA** in the sidebar.
2. Paste a NORMAL log (e.g. `INFO HTTP 200 GET /api/health`) and click
   **Classify**. Note the millisecond inference time and the green
   NORMAL badge.
3. Replace it with `ERROR Failed to connect to Redis at 10.0.1.100:6379`
   and classify again. The result flips to ERROR with `should_invoke_rca: true`.

> **Talking point:** "The classifier is a fine-tuned ModernBERT — small
> enough to run on every chunk in milliseconds. It's a cheap gate
> deciding when to spend the much-more-expensive multi-agent RCA budget."

### Act 2: Manual RCA (~1 min)

1. Click **Agent Explorer**.
2. The Redis preset is loaded by default. Click **Run RCA**.
3. Watch the four agent steps stream in: retrieval → reasoning →
   reflection → memory update.
4. Read out the final markdown summary: hypothesis citing
   `redis-conn-refused-001`, suggested actions, and the score updates
   (boosted +0.2 on the Redis incident, demoted -0.1 on the others).

> **Talking point:** "Each pipeline run has four phases. Reflection is
> what makes the memory dynamic — incidents that helped the diagnosis
> get boosted, irrelevant ones get demoted. Over time the retrieval
> tool is biased towards what historically worked."

### Act 3: Live monitoring with auto-RCA (~3 min)

1. Click **Live Monitoring** in the sidebar.
2. Confirm both toggles are on: **Auto-classify** and **Auto-RCA**.
3. Click **Start**. The simulator begins generating chunks every 3s.
4. Watch the **Event feed** column. Most chunks are NORMAL/WARNING and
   classify in milliseconds — no RCA fires.
5. When an ERROR or FATAL chunk arrives (typically within ~20s of
   running on the `mixed` profile), the **Investigations** tab on the
   right auto-flips into view. A new investigation appears with status
   "queued", then "running", then "done".
6. Expand the completed investigation to show the full agent timeline
   inline with the simulator.

> **Talking point:** "Notice how the gating works in practice. We're
> firing one Gemini call every few seconds for classification — that's
> cheap. But we only invoke the four-agent RCA pipeline when the
> classifier flags a real incident. That keeps token costs bounded
> proportionally to actual problem rate, not log volume."

### Act 4: History replay (~30s)

1. Click **Incident History**.
2. The just-completed automated investigations show up alongside any
   manual runs from earlier.
3. Click **Open** on one of them — the saved ADK session is fetched
   from the agent service and the timeline + final markdown render
   exactly as they did live.

> **Talking point:** "Every session is replayable. We don't store the
> agent's text twice — what you're seeing is the same `aggregateEvents`
> function reducing the persisted ADK event log into the same view."

### Act 5: Reset for the next demo (~10s)

If you're running the demo back-to-back, score drift accumulates and
the next run won't be as clean. To reset:

```bash
curl -X POST http://localhost:8000/demo/reset-memory
```

The endpoint returns `{"status":"ok","count":6}` once seeded. (Requires
`ALLOW_DEMO_RESET=1` set when starting the agent service.)

## Troubleshooting

- **Both pills stay grey ("Checking…")**: the frontend can't reach the
  backends. Check ports 8000 and 8001 are bound and not blocked.
- **"Auto-RCA" runs but nothing appears**: check the agent service log
  for Gemini auth errors. The free tier rate-limits at ~15 RPM; if
  you've been demo'ing repeatedly you may be throttled.
- **Stale memory state from previous runs**: hit
  `/demo/reset-memory` (above) or run `uv run python
  scripts/reset_memory.py` from the `rca-agent-system` directory.
- **Frontend won't build**: run `pnpm install` in `frontend/` first;
  `package.json` may have changed since your last fetch.
