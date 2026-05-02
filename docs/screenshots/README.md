# Screenshots

Drop the thesis-ready screenshots and demo recording here. The README
above (`docs/DEMO.md`) walks through the demo in five acts; capture
one image per act plus a short GIF of the automation loop.

## Suggested set

| Filename | Captures |
|---|---|
| `01-classifier-page.png` | `/classify` after pasting a Redis ERROR chunk and pressing Classify; the result shows `severity: ERROR` + `should_invoke_rca: true`. |
| `02-agent-explorer-streaming.png` | `/agent-explorer` mid-RCA, with the four step cards visible and the final Markdown card just rendering. |
| `03-monitoring-investigations.png` | `/monitoring` with at least one `done` investigation in the right panel and several normal classifications in the feed. |
| `04-incidents-replay.png` | `/incidents/[id]` showing a replayed session timeline. |
| `05-memory-update-card.png` | Close-up of the `## Memory updates` section of a final RCA, showing the per-incident `old → new (Δ)` lines. |
| `automation-loop.gif` | 30-60s recording of the full automation loop on `/monitoring` — chunks classify cheaply until an ERROR fires the RCA. |

## Capture tips

- macOS: `Cmd+Shift+5` or [Kap](https://getkap.co) for GIFs.
- Disable system notifications and bookmarks bar for cleaner shots.
- Resize the browser to ~1280×800 so screenshots fit in two-column
  thesis layouts without aggressive scaling.
- For the GIF, frame just the right side of `/monitoring` (event feed
  + Investigations tab) so the action is centred.

## Where they're referenced

- `docs/DEMO.md` — runbook prose can link these inline once they exist.
- The thesis "System Walkthrough" / evaluation chapter — pick 3-4 to
  illustrate the demo flow.
