# frontend

Next.js 16 / React 19 app that surfaces the rest of the system. It
talks to the classifier on `:8001` and the agent service on `:8000`
and renders four pages.

## Pages

| Route | Purpose |
|---|---|
| `/` | Landing card with links to the other pages and a short orientation. |
| `/classify` | Manual playground for the classifier. Paste a chunk; see severity, confidence, all-class probabilities, and inference time. |
| `/agent-explorer` | Manual single-shot RCA. Paste a log chunk, watch the four-stage pipeline stream live in a per-agent timeline, get the final Markdown summary. |
| `/monitoring` | Live log simulator. Generates synthetic chunks, classifies them, and (when **Auto-RCA** is on) automatically queues an investigation for any ERROR/FATAL chunk. The right-hand tab toggles between a Latest-event card and a queued Investigations list. |
| `/incidents` | Browser-local history of recent runs (live + auto-fired). Each link opens `/incidents/[id]`, which fetches the saved ADK session and replays it through the same timeline component. |

The top nav has two health pills (Classifier, Agent) that turn green
when each backend's `/health` endpoint reports OK.

## Architecture notes

- **SSE for agent streaming.** ADK's `/run_sse` is a POST with a JSON
  body, so the browser `EventSource` API can't be used. Instead we
  do `fetch` + `ReadableStream` reader and split on `\n\n` blocks.
  See [`src/lib/api/agents.ts`](./src/lib/api/agents.ts).
- **Per-agent aggregation.** Raw ADK events stream at 50–150 events
  per pipeline run (most are `partial: true` text fragments). The
  hook [`useAgentStream`](./src/lib/hooks/useAgentStream.ts) groups
  them by `event.author`, concatenates partial text, dedupes tool
  calls by id, and exposes `groups: AgentRunGroup[]`. The same pure
  `aggregateEvents` function powers replay on `/incidents/[id]`.
- **Sequential auto-RCA queue.** [`useInvestigationsQueue`](./src/lib/hooks/useInvestigationsQueue.ts)
  watches `sim.events`, dedupes by SimEvent id, and enforces
  one-at-a-time execution via a `runningRef` guard. Memory bounds:
  ≤ 30 investigations, ≤ 500 raw events each.

## Install & run

```bash
pnpm install
pnpm dev          # http://localhost:3000
```

The two backends are not embedded — start them in separate terminals
or use the repo-root `just dev` (see top-level README).

## Environment variables

Drop into `frontend/.env.local` (gitignored). All `NEXT_PUBLIC_*` vars
are exposed to the browser.

| Var | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CLASSIFIER_URL` | `http://localhost:8001` | Base URL of the classifier service. |
| `NEXT_PUBLIC_AGENT_URL` | `http://localhost:8000` | Base URL of the rca-agent-system. |
| `NEXT_PUBLIC_USE_MOCK` | `false` | When `"true"`, skips the network and uses a keyword-based mock classifier. Handy for offline dev. |

A template lives at [`.env.local.example`](./.env.local.example) with
the same defaults documented inline.

## Tests

```bash
pnpm test          # vitest run
pnpm test:watch
```

The suite runs against jsdom with `@testing-library/react`. Hooks are
exercised via `renderHook`; SSE streaming is mocked by piping
hand-crafted `data: {...}\n\n` blocks through a `ReadableStream` so the
real parser is exercised.

## Build

```bash
pnpm build         # next build (Turbopack)
```

The build runs full TypeScript checking and prerenders 6 of the 7
routes statically. `/incidents/[id]` is server-rendered on demand
because it fetches a session by id at request time.

## Common issues

- **Both pills stay grey ("Checking…")**: the frontend can't reach
  one or both backends. Make sure they're listening on `:8000` and
  `:8001` and not blocked by a firewall. Check the dev console for
  CORS errors.
- **Browser preview shows HMR warnings about cross-origin fetch**:
  Next.js 16 blocks dev assets from origins it didn't bind. We
  whitelist `127.0.0.1` and `localhost` via `allowedDevOrigins` in
  `next.config.ts`. Restart the dev server after editing that file.
- **`pnpm test` fails on hooks with timeouts**: the health hooks use
  `retry: 1` which costs ~1s of backoff per failed attempt. Tests
  using these hooks should pass `intervalMs: 100_000` and
  `waitFor(..., { timeout: 3000 })`. Pattern is in
  `useClassifierHealth.test.tsx`.
