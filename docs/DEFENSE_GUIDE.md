# Thesis Defense — Setup & Demo Bible

A single document covering: (1) installing the project on a fresh
Windows laptop (Acer Aspire, i3), (2) pre-defense warm-up, (3) the
live demo script with exact phrases per act, (4) Q&A preparation,
(5) emergency recovery.

> **Read this end-to-end at least 24 hours before the defense.** Run
> the setup section the day before. Run the warm-up ~30 minutes
> before you walk in.

---

## Table of contents

1. [Hardware & expectations on an i3](#part-1--hardware--expectations-on-an-i3)
2. [One-time setup](#part-2--one-time-setup-do-this-the-day-before)
3. [Pre-defense warm-up](#part-3--pre-defense-warm-up-30-minutes-before)
4. [Demo script with talking points](#part-4--demo-script-with-talking-points)
5. [Q&A preparation](#part-5--qa-preparation)
6. [Emergency troubleshooting](#part-6--emergency-troubleshooting)
7. [Post-defense cleanup](#part-7--post-defense)

---

# Part 1 — Hardware & expectations on an i3

| Component | Where work happens | Cost on i3 |
|---|---|---|
| ModernBERT classifier | Local CPU inference | **~200-500ms/chunk** (vs ~50ms on MPS). First load 10-30s. |
| ChromaDB retrieval | Local CPU + disk | Negligible (< 50ms). |
| Gemini agents (4 sub-agents) | **Remote** Google servers | Network bound, ~30-60s/RCA. **i3 doesn't matter here.** |
| Frontend (Next.js dev) | Local Node | Fine on i3. |

> **Key insight.** The expensive part is the Gemini round-trip,
> which doesn't depend on your laptop. **Don't apologize for the
> hardware in your defense.**

## Pre-flight check

- [ ] **Charger plugged in.** Battery throttling makes the classifier sluggish.
- [ ] **Stable internet** (Gemini calls). Phone hotspot as backup.
- [ ] **Free RAM ≥ 2 GB**: close Chrome tabs, Discord, OneDrive sync.
- [ ] **Free disk ≥ 3 GB**.
- [ ] **Time-zone correct** (TLS cert checks fail with a wrong clock).

---

# Part 2 — One-time setup (do this the day before)

Estimated time: **45-90 minutes**.

## 2.1 — Install prerequisites

### Git for Windows
<https://git-scm.com/download/win>. **Accept the default that adds
Git Bash and `git` to PATH.** Use **Git Bash** as your primary
terminal — the `run-all.sh` orchestration script is bash.

### Python 3.11 or 3.12
<https://www.python.org/downloads/windows/>. **Tick "Add Python to
PATH"**. Verify: `python --version`.

### uv (fast Python package manager)
In **PowerShell**:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
Restart terminal. Verify: `uv --version`.

### Node.js 20+ LTS
<https://nodejs.org/>. Install with defaults. Verify: `node --version`.

### pnpm
```powershell
npm install -g pnpm
pnpm --version    # 9.x or higher
```

### Gemini API key
1. <https://aistudio.google.com/apikey>
2. Sign in, click **Create API key**, copy it (starts with `AIza…`).
3. **Save it in a password manager.**

> Free tier: 15 RPM, 1M tokens/day. A full RCA uses ~4 calls. Don't
> burn the eval suite the morning of the defense.

## 2.2 — Get the classifier model file

The fine-tuned ModernBERT is **gitignored** (~150 MB). Copy it from
your training environment / USB / Drive to:

```
classifier-service/models/modernbert-log-severity-v1/
├── config.json
├── model.safetensors           (or pytorch_model.bin)
├── tokenizer.json
├── tokenizer_config.json
└── training_metadata.json
```

**Without this directory, the classifier service will not start.**
Get it sorted before continuing.

## 2.3 — Clone and install

> **THIS IS A MONOREPO — there is no `pyproject.toml` at the repo
> root.** Each of `classifier-service/`, `rca-agent-system/`, and
> `frontend/` is its own project with its own dependencies. **Never
> run `uv sync` or `pip install` at the repo root** — you'll get
> `error: No pyproject.toml found`. Always `cd` into a sub-project
> first.

> **Avoid paths with spaces** if you can (e.g. `Research Project`).
> Most tools handle them, but a few break in subtle ways on Windows.
> Either rename the parent folder or use a path like `C:\projects\...`.
> If you must use a path with spaces, the commands below still work
> as long as you `cd` from the prompt (PowerShell handles the
> quoting for you).

> **Avoid OneDrive / Dropbox folders.** They intercept file writes
> and break virtual-environment resolution on Windows.

### Clone

Open a terminal (**Git Bash** preferred for the demo, but
**PowerShell** is fine for installation).

**Git Bash:**
```bash
cd /c/projects     # or wherever you want it
git clone https://github.com/Wathsu4/Reflection-Enhanced-Multi-Agent-RAG-RCA.git
cd Reflection-Enhanced-Multi-Agent-RAG-RCA
```

**PowerShell:**
```powershell
cd C:\projects     # or wherever you want it
git clone https://github.com/Wathsu4/Reflection-Enhanced-Multi-Agent-RAG-RCA.git
cd Reflection-Enhanced-Multi-Agent-RAG-RCA
```

Drop the model directory you copied in step 2.2 into:

```
classifier-service\models\modernbert-log-severity-v1\
```

### Install — three sub-projects, run in order (5-15 min)

Run each block from the **repo root**. `uv sync` will create a
`.venv` *inside* each sub-project automatically; you don't need to
`python -m venv` or `Activate.ps1` yourself.

> **Use `--extra dev` for both Python sub-projects.** It pulls in
> `pytest` (needed for the validation step below) along with `ruff`
> and `pyright`. Skipping it gives you `error: Failed to spawn:
> pytest, Caused by: program not found` when you try to run tests.

**PowerShell (one command per line — `&&` chaining is PowerShell 7
only and unreliable on default Windows installs):**

```powershell
cd classifier-service
uv sync --extra dev
cd ..

cd rca-agent-system
uv sync --extra dev
cd ..

cd frontend
pnpm install
cd ..
```

**Git Bash (or PowerShell 7+) — same thing as a one-liner per project:**

```bash
cd classifier-service && uv sync --extra dev && cd ..
cd rca-agent-system && uv sync --extra dev && cd ..
cd frontend && pnpm install && cd ..
```

To run anything inside a sub-project later, `cd` into it and use
`uv run`:

```powershell
cd rca-agent-system
uv run python scripts/seed_knowledge_base.py
uv run python server.py
```

You should never need to manually activate a venv with `uv`.

## 2.4 — Configure secrets

**Git Bash:**
```bash
cd rca-agent-system
cp .env.example .env
```

**PowerShell:**
```powershell
cd rca-agent-system
Copy-Item .env.example .env
```

Edit `rca-agent-system/.env` (Notepad, VS Code, anything):

```env
GOOGLE_API_KEY=AIza...PASTE-YOUR-KEY-HERE
ALLOW_DEMO_RESET=1
```

Other values keep defaults.

> `ALLOW_DEMO_RESET=1` enables `POST /demo/reset-memory`, the
> easiest way to wipe state between demo attempts.

## 2.5 — Seed the knowledge base

First run downloads ChromaDB's embedding model (~90 MB). Be patient.

```bash
# Still in rca-agent-system/
uv run python scripts/seed_knowledge_base.py
# Expect: "Seeded 6 incident(s). Collection now contains 6 entries."
```

If you see fewer than 6, run `scripts/reset_memory.py` and retry.

## 2.6 — Validate

Run from the **repo root**, one block at a time:

**PowerShell:**
```powershell
cd frontend
pnpm test          # expect: 145 passed
cd ..

cd classifier-service
uv run pytest -q   # expect: 9 passed
cd ..

cd rca-agent-system
uv run pytest -q   # expect: 85 passed
cd ..
```

**Git Bash:**
```bash
cd frontend && pnpm test && cd ..
cd classifier-service && uv run pytest -q && cd ..
cd rca-agent-system && uv run pytest -q && cd ..
```

**Total: 239 tests should pass.** If any fail, fix it now — not on
defense day. See [Part 6](#part-6--emergency-troubleshooting).

## 2.7 — Smoke test the live system

Three Git Bash terminals.

**Terminal 1 — classifier:**
```bash
cd /c/projects/Reflection-Enhanced-Multi-Agent-RAG-RCA/classifier-service
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```
Wait for `Model loaded on device=cpu` (~30s on i3 first run).

**Terminal 2 — agent service:**
```bash
cd /c/projects/Reflection-Enhanced-Multi-Agent-RAG-RCA/rca-agent-system
uv run python server.py
```
Wait for `Application startup complete.`.

**Terminal 3 — frontend:**
```bash
cd /c/projects/Reflection-Enhanced-Multi-Agent-RAG-RCA/frontend
pnpm dev
```
Wait for `Ready in ...`. Open <http://localhost:3000>.

**Smoke checklist:**
- [ ] Both health pills turn **green** within 10s.
- [ ] `/classify` with `ERROR Failed to connect to Redis at 10.0.1.100:6379`
      → result: ERROR + `should_invoke_rca: true`.
- [ ] `/agent-explorer` → click **Run RCA** → all four steps complete +
      final Markdown summary (~30-60s).
- [ ] `/monitoring` → **Start** with `mixed` profile → an
      investigation auto-fires within ~30s.
- [ ] `/incidents` → recent runs listed; clicking one replays correctly.

If all green, **you are ready.** Stop the services (`Ctrl+C` each).

---

# Part 3 — Pre-defense warm-up (30 minutes before)

This turns "kind of works" into "production-quality" demo. Follow it
exactly.

## 3.1 — Reset memory (T-30 min)

Every demo starts from the same baseline:

```bash
cd /c/projects/Reflection-Enhanced-Multi-Agent-RAG-RCA/rca-agent-system
uv run python scripts/reset_memory.py
```

Without this, score drift from previous attempts will bias today's
retrieval and confuse the demo.

## 3.2 — Start all services (T-25 min)

Single command (Git Bash):
```bash
# Repo root
bash scripts/run-all.sh dev
```

Wait for:
- `Model loaded on device=cpu` — classifier ready
- `Application startup complete.` — agent ready
- `Ready in ...` — frontend ready

Open <http://localhost:3000>. Both pills must be green.

## 3.3 — Pre-warm Gemini (T-15 min)

Cold-starting Gemini on stage is awkward. Off-camera, do one full
RCA now to warm the model.

1. Go to `/agent-explorer`.
2. Click **Run RCA** with the default Redis preset.
3. Wait ~30-60s for completion.
4. Don't worry about score updates — you'll reset again.

## 3.4 — Pre-classify (T-10 min)

Classifier's first CPU inference is slow (kernel JIT). Warm it:

1. `/classify`, paste and submit each, in turn:
   - `INFO HTTP 200 GET /api/health`
   - `WARN Slow query: 2.4s on user_table`
   - `ERROR Failed to connect to Redis at 10.0.1.100:6379`
2. Confirm third call's inference time is < 200ms.

## 3.5 — Final reset (T-5 min) — **CRITICAL**

The pre-warm in 3.3 mutated memory scores. Reset so the live demo
starts from baseline:

```bash
curl -X POST http://localhost:8000/demo/reset-memory
# {"status":"ok","count":6}
```

> **Do NOT restart the services after this reset.** The classifier
> and Gemini are still warm; only memory was wiped.

## 3.6 — Browser hygiene (T-3 min)

- Close every browser tab except the demo.
- Disable extensions that inject UI (LastPass, ad-blockers).
- Hide bookmarks bar (`Ctrl+Shift+B`).
- Set zoom **110-125%** for back-row visibility.
- **Open these four tabs in this order, left to right:**
  1. <http://localhost:3000/classify>
  2. <http://localhost:3000/agent-explorer>
  3. <http://localhost:3000/monitoring>
  4. <http://localhost:3000/incidents>

## 3.7 — Have ready in clipboard / notes

```bash
# Reset between attempts during questions
curl -X POST http://localhost:8000/demo/reset-memory

# Open eval reports if asked about results
explorer rca-agent-system\eval
```

## 3.8 — Final checklist (T-1 min)

- [ ] Both health pills green
- [ ] Tabs in correct order
- [ ] Memory just reset, services warm
- [ ] Phone on silent
- [ ] Charger plugged in (not battery)
- [ ] Sip of water taken

You're ready.

---

# Part 4 — Demo script with talking points

This is a **5-act demo** that maps directly onto your research questions.
Total time: **8-12 minutes**, leaving room for Q&A.

For each act:
- **DO:** the click-by-click action.
- **SAY:** verbatim phrasing. Memorize the **bold** sentences;
  paraphrase the rest.
- **WHY IT SCORES:** the implicit claim each act demonstrates.

> **General delivery tips:**
> - Speak slower than feels natural.
> - **Always say what you're about to do BEFORE you click.**
> - Use "the system" not "my code" — research, not programming.
> - During streaming pauses, set up the next point. Don't apologize.

## Opening (45 seconds)

**SAY:**

> "My project is an automated root-cause analysis system that pairs a
> small log-severity classifier with a multi-agent RAG pipeline whose
> memory of past incidents adapts over time through a reflective
> feedback loop.
>
> **The novelty claim is in the memory loop:** rather than a static
> retrieval index, each completed analysis updates per-incident
> relevance scores, so the system biases towards incidents that have
> historically been useful — without retraining anything.
>
> I'll demonstrate this in five short acts: manual classification,
> manual RCA, the live monitoring loop, history replay, and finally
> the memory evolution that backs the novelty claim."

**WHY IT SCORES:** You've stated the *what*, the *why it's novel*, and
the *demo structure* in 45 seconds. Examiners now know what to listen
for.

---

## Act 1 — Manual classification (~60 seconds)

**Switch to tab 1: `/classify`.**

**SAY:**

> "Before any expensive reasoning happens, every log chunk goes through
> a fine-tuned ModernBERT classifier. This is the **gate** that decides
> whether to spend further compute."

**DO:** Paste:
```
INFO HTTP 200 GET /api/health
INFO User session refreshed
DEBUG Cache hit ratio 94%
```
**DO:** Click **Classify**.

**SAY:**

> "Healthy traffic. NORMAL with high confidence, well under 100
> milliseconds of inference. Crucially, `should_invoke_rca` is
> **false** — the multi-agent pipeline is not invoked, so this chunk
> costs almost nothing."

**DO:** Replace with:
```
2024-01-15 16:30:01 ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused
2024-01-15 16:30:02 INFO  Retrying connection (attempt 1/3)
2024-01-15 16:30:05 ERROR Retry failed: Connection refused
```
**DO:** Click **Classify**.

**SAY:**

> "Same model, very different output. ERROR with high confidence, and
> now `should_invoke_rca` is **true**. **This two-stage architecture
> is what bounds the system's cost** — Gemini calls scale with the
> incident rate, not with raw log volume. That answers research
> question four."

**WHY IT SCORES:** You introduced gating and explicitly mapped to RQ4.

---

## Act 2 — Manual single-shot RCA (~90 seconds)

**Switch to tab 2: `/agent-explorer`.**

**SAY:**

> "When the gate fires, the chunk lands in a four-agent pipeline.
> Each agent has a single specialised job, and outputs flow through
> a typed session-state channel."

**DO:** Click **Run RCA** (Redis preset is loaded by default).

**SAY (while it streams):**

> "The first agent — **retrieval** — pulls top-k similar past
> incidents from a ChromaDB vector store. The second — **reasoning**
> — produces a structured root-cause hypothesis citing those
> incidents. The third — **reflection** — judges *which* of the
> retrieved incidents actually informed the diagnosis, and emits
> per-incident relevance deltas in the range minus point two to plus
> point two. The fourth — **memory update** — writes those deltas
> back to ChromaDB and produces the final Markdown report.
>
> This separation of concerns is what makes the reasoning trace
> auditable. **Every claim in the final report is traceable to a
> specific agent's output.** That answers research question two."

**DO:** When done, scroll to **`## Root cause`** in the final card.

**SAY:**

> "Notice the hypothesis cites `redis-conn-refused-001` by ID — that's
> not a hallucination, it's a structured citation from the retrieval
> output."

**DO:** Scroll to **`## Memory updates`**.

**SAY:**

> "And here's the closed loop. The reflection agent boosted the Redis
> incident's success score by zero point two and demoted four
> irrelevant incidents by zero point one each. The next time a similar
> error comes in, the retrieval re-ranking will favour this incident
> proportionally more. **This is the novelty contribution of this
> work.**"

**WHY IT SCORES:** You've now demonstrated RQ1 (reflection scores
retrieval), RQ2 (multi-agent), RQ3 (dynamic memory), RO2 (closed loop)
in one act.

---

## Act 3 — Live monitoring with auto-RCA (~3 minutes)

**Switch to tab 3: `/monitoring`.**

**SAY:**

> "So far I've shown components in isolation. Here's what happens when
> they run together as a streaming pipeline. The simulator generates
> synthetic log chunks, the classifier gates each one, and any chunk
> flagged ERROR or FATAL automatically queues an investigation."

**DO:** Confirm both toggles on (Auto-classify, Auto-RCA). Click
**Start** with `mixed` profile.

**SAY (while chunks stream):**

> "Most of these are NORMAL or WARNING — classified in milliseconds,
> dropped, no agent calls. **No tokens spent.**"

Wait for an ERROR/FATAL chunk to fire an investigation. The right tab
auto-flips to "Investigations".

**SAY (when one appears):**

> "There — that ERROR chunk just triggered an automatic investigation.
> Notice the simulator keeps running, classifying new chunks
> independently, while the agent pipeline runs in the background. The
> investigations queue is **strictly sequential** — one Gemini-bound
> pipeline at a time — to respect rate limits and keep the demo
> reproducible."

**SAY (continue while it runs):**

> "An important design detail: the simulator could fire multiple
> investigations per minute on a noisy production stream. The queue
> with a single concurrent slot makes the system's compute bound a
> linear function of *incident* rate, not log rate. That's what makes
> classifier-gated RCA tractable in production."

**DO:** When the investigation completes, expand it.

**SAY:**

> "The expanded view is the same agent timeline component from the
> manual page — full reasoning trace, citations, structured root
> cause. Operationally, this is what an on-call engineer would see in
> a real monitoring tool."

**DO:** Toggle Auto-RCA off.

**SAY:**

> "And if I disable Auto-RCA, the classifier keeps running but no new
> investigations fire — useful in production for gracefully draining
> Gemini quota during a noisy incident."

**DO:** Click **Stop** to halt the simulator.

**WHY IT SCORES:** You've shown the *integrated* system, demonstrated
production concerns (rate limiting, graceful degradation), and mapped
to RQ4. The architecture is no longer abstract.

---

## Act 4 — History replay (~45 seconds)

**Switch to tab 4: `/incidents`.**

**SAY:**

> "Every pipeline run is persisted as an ADK session. This page
> reconstructs them from the saved event log."

**DO:** Click **Open** on the most recent investigation.

**SAY:**

> "What you're seeing is the same timeline component as the live page,
> but driven from a fetched session. **There's only one rendering
> path** — `aggregateEvents` reduces raw ADK events into per-agent
> groups identically for live and replay. That guarantees what an
> operator saw at incident time is exactly what an auditor sees later."

**WHY IT SCORES:** Auditability is a serious-systems concern that
distinguishes a research prototype from a toy.

---

## Act 5 — Memory evolution — THE HEADLINE (~90 seconds)

**This is the most important act. It backs your novelty claim.**

Two options. Pick by time + Gemini quota remaining.

### Option A — Show pre-computed results (safer, recommended)

**SAY:**

> "Finally, the memory-evolution experiment that quantifies the
> novelty claim. Running the full eval live takes about ten minutes,
> so I'll show the results from a clean run I executed earlier."

**DO:** Open `rca-agent-system/eval/memory-evolution-{timestamp}.md`
in your editor or browser.

**SAY (pointing at the table):**

> "I ran the in-domain subset of the evaluation set through the
> pipeline twice, against a clean baseline where every incident
> starts at score one point zero. **The drift summary at the bottom
> shows the exact pattern the architecture predicts:** incidents the
> reasoning agent correctly leaned on are boosted, irrelevant
> incidents are demoted, and the direction of drift is reproducible
> across runs."
>
> "This is the closed feedback loop in numerical form. **It is the
> evidence for research question three and research objective two.**"

### Option B — Live demonstration (only with time + quota)

**DO:** Switch to `/agent-explorer`. Run the same Redis preset again.
Point to `## Memory updates` in the result.

**SAY:**

> "Same input, same retrieval — but now look at the score on the Redis
> incident. It started at one point two from our earlier run, and
> reflection boosted it again. **The score has evolved dynamically
> across runs without any retraining.** Multiply this across hundreds
> of incidents and the retrieval index becomes measurably better at
> surfacing useful past incidents."

**WHY IT SCORES:** Numerical evidence, not just architectural claims.
This act distinguishes a passing thesis from a distinction-grade one.

---

## Closing (30 seconds)

**SAY:**

> "To summarise: the system is a classifier-gated multi-agent pipeline
> with a reflection-driven dynamic memory. The classifier bounds cost.
> The agent specialisation gives an auditable reasoning trace. The
> reflection loop turns the memory into a learning component without
> retraining.
>
> The full evaluation, including LLM-as-judge accuracy, retrieval
> recall, and per-incident score drift, is in the thesis appendix
> with source data under `rca-agent-system/eval/`.
>
> I'm happy to take questions."

**WHY IT SCORES:** You've recapped *why* each architectural choice
exists and explicitly invited questions on the parts you're most
confident defending.

---

# Part 5 — Q&A preparation

Likely questions with tight, defensible answers. Memorize the **bold**
core sentence; expand if pressed.

## Architecture / design

**Q: Why ModernBERT and not a larger LLM for classification?**

> "**The classifier's job is gating, not analysis.** A 150-million-
> parameter ModernBERT runs in under a second on CPU and answers a
> four-class question with high accuracy. Putting Gemini on every
> chunk would invert the cost curve — the cheap part would dominate.
> ModernBERT keeps gating proportional to log volume and the
> expensive part proportional to incident rate."

**Q: Why a SequentialAgent and not a parallel multi-agent setup?**

> "**Reasoning has data dependencies on retrieval, and reflection has
> dependencies on both.** Parallelising them would mean reasoning
> without retrieved context, which defeats the RAG part. The
> sequential graph gives us the typed session-state channel that
> makes the trace auditable."

**Q: How is this different from a single Gemini call with a long prompt?**

> "**Single-call setups conflate retrieval, hypothesis, and self-
> evaluation into one black box.** With four specialised agents we
> get separate intermediate artefacts — retrieval output, hypothesis,
> reflection, final report — each independently testable. We also
> get a place to put the dynamic memory mutation, which has nowhere
> to live in a one-shot prompt."

## Memory / novelty

**Q: How do you know score updates aren't random noise?**

> "**The memory-evolution evaluation runs the same in-domain
> scenarios twice and measures whether the *direction* of drift is
> consistent.** A noise process produces roughly equal probability of
> boost vs demote per incident; a real signal produces consistent
> direction. The drift-summary numbers in
> `eval/memory-evolution-{timestamp}.md` show that signal."

**Q: What stops a malicious or incorrect reflection from poisoning memory?**

> "**Two safeguards.** First, deltas are clamped to plus-or-minus
> zero point two per call, so no single reflection can dominate.
> Second, scores are clamped to zero through two, so a bad streak
> can't drive an incident negative or unboundedly large. A more
> robust production version would add cool-downs and per-source rate
> limits, which the architecture supports but I didn't implement for
> the prototype."

**Q: What if all seeded incidents are irrelevant to a real production log?**

> "**That's exactly what the out-of-distribution scenarios in the eval
> dataset test.** Retrieval similarity stays low, the reasoning agent's
> hypothesis is correspondingly weaker, and reflection records small
> or zero deltas. The system fails honestly rather than confabulating
> a citation. The OOD entries in `eval/incidents.jsonl` have
> `expected_incident_id: null`."

## Evaluation

**Q: Why keyword-overlap as the primary metric? It seems crude.**

> "**Because it's deterministic and reproducible.** LLM-as-judge
> floors out around 80-90% accuracy even for human-perfect
> hypotheses, which makes it a noisy primary metric. Keyword score is
> conservative — it under-rewards correct paraphrases — but a
> hypothesis that misses every domain-expert keyword is genuinely
> wrong. I report both; keyword is the floor."

**Q: How big is your evaluation set, and is that enough?**

> "**Fifteen scenarios — twelve in-domain, two paraphrased per seeded
> incident type, plus three out-of-distribution.** Enough to show the
> architectural claims: recall, drift direction, OOD handling. Not
> enough to claim a production accuracy number, which I'm explicit
> about in the thesis. Scaling the eval set is the obvious future-
> work item."

**Q: How long does a full pipeline run take?**

> "**Around thirty to sixty seconds end-to-end on free-tier Gemini.**
> The classifier adds about fifty milliseconds. The dominant cost is
> Gemini RTT, which is network bound and largely insensitive to the
> rest of the system."

## Implementation

**Q: Why ChromaDB and not a real production vector DB?**

> "**Local-first development and zero-ops setup.** ChromaDB is
> embedded, persists to disk, and lets the entire stack run on a
> laptop. The retrieval interface in `tools/retrieve_incidents.py` is
> small enough that swapping in a managed vector store would be a
> drop-in change."

**Q: Can the system be deployed to production?**

> "**The pieces that would be touched are clearly scoped.** The
> classifier is a FastAPI service ready to scale horizontally; the
> agent service is FastAPI on top of Google ADK with session
> persistence; memory is a vector store with a clean interface. The
> thesis is a research prototype, but architectural seams were chosen
> with deployability in mind."

**Q: How did you handle Gemini rate limits during evaluation?**

> "**The investigations queue enforces strict sequential execution
> with a single concurrent slot.** Free-tier Gemini permits roughly
> fifteen requests per minute; a four-agent pipeline burns four, so I
> get one full RCA every fifteen seconds at peak. The queue also
> dedupes by event id so flapping classifications can't trigger
> duplicate runs."

## Curveballs

**Q: What's the limitation of this approach you're most aware of?**

> "**The reflection agent is itself a Gemini call, so the quality of
> the score signal is bounded by Gemini's calibration.** A reflection
> that misjudges relevance produces a wrong score update. Mitigation
> is the per-call delta clamp, but a stronger system would use
> multiple reflection samples and aggregate. I report this explicitly
> in the limitations section of the thesis."

**Q: What if you don't know the answer?**

> Buy time honestly: **"That's a good question — let me think for a
> second."** Then either answer if you can, or **"I don't have a
> clean answer to that, but my best understanding is X."** Faking
> certainty is the fastest way to lose marks. Examiners reward
> calibrated uncertainty.

---

# Part 6 — Emergency troubleshooting

Things that can go wrong on the day, and recovery without disrupting
demo flow.

## Setup-time errors (Part 2 install)

### `error: No pyproject.toml found in current directory or any parent directory`

**Cause:** you ran `uv sync` (or `pip install -e .`) from the **repo
root**. This is a monorepo — there's no top-level `pyproject.toml`
by design. Each sub-project has its own.

**Fix:**
```powershell
# If you accidentally created a venv at the root, remove it:
deactivate                              # only if a venv is active
Remove-Item -Recurse -Force .venv       # PowerShell
# (Git Bash: rm -rf .venv)

# Then install per sub-project:
cd classifier-service ; uv sync ; cd ..
cd rca-agent-system ; uv sync --extra dev ; cd ..
cd frontend ; pnpm install ; cd ..
```

`uv` creates a `.venv` *inside* each sub-project. You don't run
`python -m venv` or `Activate.ps1` yourself.

### `cp : The term 'cp' is not recognized` (PowerShell)

**Cause:** `cp` is a Unix command. PowerShell aliases it on most
modern setups, but not always.

**Fix:** Use `Copy-Item` instead, or just create the `.env` in any
text editor by saving a copy of `.env.example` as `.env`.

### `pnpm : The term 'pnpm' is not recognized`

**Cause:** pnpm not on PATH yet — `npm install -g pnpm` needs a new
shell to register the global binary.

**Fix:** Close the PowerShell window and open a new one. Re-run
`pnpm --version` to confirm.

### `uv : The term 'uv' is not recognized`

**Cause:** uv installer ran but PATH wasn't refreshed.

**Fix:** Close and reopen the terminal. If still missing, the
PowerShell installer added uv to `$env:USERPROFILE\.local\bin` —
verify it exists and add it to PATH manually if needed.

### `uv run pytest` → `Failed to spawn: pytest, Caused by: program not found`

**Cause:** you ran `uv sync` without `--extra dev`, so the dev tools
(`pytest`, `ruff`, `pyright`) weren't installed.

**Fix:** Re-sync with the extra:
```powershell
# In whichever sub-project you're testing
uv sync --extra dev
uv run pytest -q
```

This applies to both `classifier-service` and `rca-agent-system`.

### Tests look like they're stuck on a model download

**Cause:** the classifier-service tests instantiate the ModernBERT
model on first run, which can take 30-60s on an i3 from a cold disk
cache. Same for rca-agent-system tests, which load ChromaDB's
embedding model (~90 MB) on first run only.

**Fix:** Wait. Run the tests once during setup so the cache is warm
before you ever run them under time pressure on defense day.

---

## Demo-time errors

## "Both health pills are red"

**Cause:** backends not running, or ports blocked.

**Fix:**
```bash
netstat -ano | findstr ":8000 :8001"
```
If empty, services died. Restart per Part 3.2. If they're running but
pills red, Windows Firewall is prompting somewhere — find the popup,
click "Allow access".

## "Classifier takes 5+ seconds per chunk"

**Cause:** model still loading, or laptop on battery / thermal
throttling.

**Fix:** Don't wait silently. **SAY:** "First inference on a cold
model is slow on CPU; subsequent calls are sub-second." Continue.
Plug in the charger if you forgot.

## "Gemini returns 429 (rate limit)"

**Cause:** free-tier RPM cap hit.

**Fix:** **DON'T retry on stage** — retry will also fail. **SAY:**
"I've hit the free-tier rate limit, a known constraint of this demo
setup. I'll switch to pre-recorded results." Switch to Act 5 Option A
(saved markdown report). This is *why* you keep eval reports on disk.

## "Investigation gets stuck on 'running'"

**Cause:** Gemini timed out, or sub-agent emitted malformed response.

**Fix:** Wait one more minute (ADK has retries). If still stuck after
90s: **SAY:** "Live demos against an external LLM are inherently
variable. I'll show this from the saved history." Switch to
`/incidents` and open a previous successful run.

## "Frontend shows a blank page"

**Cause:** Next.js HMR broke, or a browser extension is interfering.

**Fix:** Hard reload (`Ctrl+Shift+R`). If still blank, kill the dev
server and restart:
```bash
# In the frontend terminal
Ctrl+C
pnpm dev
```

## "Classifier service won't start"

**Cause:** Model file missing, or PyTorch can't load it on this
Python version.

**Fix:**
```bash
ls classifier-service/models/modernbert-log-severity-v1/
# Must show config.json, model.safetensors, tokenizer.json, etc.
```
If the directory is empty, the model file wasn't copied (Part 2.2).
This is unrecoverable mid-defense — switch fully to Act 5 Option A
(pre-recorded results) and `/incidents` replay.

## "Agent service errors with `GOOGLE_API_KEY missing`"

**Cause:** `.env` not loaded, or wrong working directory.

**Fix:**
```bash
# Confirm the env file
cat rca-agent-system/.env | grep GOOGLE_API_KEY
# Must show GOOGLE_API_KEY=AIza... (not the placeholder)
```
Restart the agent service from inside `rca-agent-system/`, not from
the repo root.

## "ChromaDB error: readonly database"

**Cause:** stale process holding the lock (a previous run that wasn't
cleanly killed).

**Fix:**
```bash
# Kill any stragglers
taskkill /F /IM python.exe
# Restart agent service
```

## Last-resort recovery

If everything is broken and you have less than 2 minutes:

1. **Don't restart anything mid-demo.** Service startup is too slow.
2. **Pivot to the static evidence.** Open in your editor:
   - `rca-agent-system/eval/results-{timestamp}.md`
   - `rca-agent-system/eval/memory-evolution-{timestamp}.md`
   - `docs/RESEARCH_QUESTIONS.md`
3. **SAY:** "The live system has a transient issue, so let me walk
   through the saved evaluation artefacts that the thesis is based
   on." Then read the eval tables and explain them. **You still get
   credit for evaluation rigour even without a live demo.**

---

# Part 7 — Post-defense

After your defense:

1. **Tag the submission commit:**
   ```bash
   git tag v1.0-thesis-submission
   git push origin v1.0-thesis-submission
   ```
2. **Save the eval reports** (`rca-agent-system/eval/results-*.md`
   and `memory-evolution-*.md`) somewhere outside the repo for the
   submission package.
3. **Take screenshots** per `docs/screenshots/README.md` for the
   thesis-bound submission.
4. **Stop services** with `Ctrl+C` in each terminal.

---

## One-page cheat sheet

Keep this printed or on a second monitor:

```
PRE-DEMO (T-30 to T-0)
  cd rca-agent-system && uv run python scripts/reset_memory.py
  bash scripts/run-all.sh dev
  /agent-explorer → Run RCA (warm Gemini)
  /classify → 3 paste-and-classify runs (warm classifier)
  curl -X POST http://localhost:8000/demo/reset-memory
  Tabs: classify → agent-explorer → monitoring → incidents

ACT TIMINGS
  Opening              0:45
  Act 1 Classify       1:00
  Act 2 Manual RCA     1:30  (longest stream)
  Act 3 Monitoring     3:00  (longest)
  Act 4 Replay         0:45
  Act 5 Memory         1:30
  Closing              0:30
  TOTAL               ~9 min, leaves time for Q&A

KEY PHRASES TO LAND
  "novelty claim is in the memory loop"
  "two-stage architecture bounds cost"
  "every claim traceable to a specific agent"
  "reproducible direction of drift"
  "research question three and research objective two"

EMERGENCY
  Gemini 429        → Act 5 Option A (saved markdown)
  Stuck investigation → /incidents replay
  Service crashed   → DON'T restart mid-demo, pivot to evals
```
