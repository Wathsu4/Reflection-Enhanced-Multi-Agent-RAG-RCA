"use client";

/**
 * Incident History page.
 *
 * Strategy: rather than depending on ADK's `/sessions` list endpoint
 * (which is per-process and resets when the server restarts), we keep
 * a small client-side cache of recent runs in localStorage and let
 * users open any of them by id. A free-text "open by id" form covers
 * the case of a session id pasted from elsewhere.
 *
 * Clicking a saved run navigates to /incidents/[id] where the same
 * AgentTimeline component replays the saved events.
 */

import { ClipboardList, ExternalLink, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const LAST_RUNS_KEY = "rca:last-sessions";

interface LastRunEntry {
  sessionId: string;
  preview: string;
  ts: number;
}

function loadLastRuns(): LastRunEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LAST_RUNS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as LastRunEntry[]) : [];
  } catch {
    return [];
  }
}

function clearLastRuns(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LAST_RUNS_KEY);
}

function formatRelative(ts: number): string {
  const delta = Date.now() - ts;
  if (delta < 60_000) return "just now";
  const mins = Math.round(delta / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export default function IncidentsPage() {
  const [runs, setRuns] = useState<LastRunEntry[]>([]);
  const [openId, setOpenId] = useState("");

  useEffect(() => {
    setRuns(loadLastRuns());
  }, []);

  const handleClear = () => {
    clearLastRuns();
    setRuns([]);
  };

  return (
    <div className="flex flex-1 flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5" />
            Incident History
          </CardTitle>
          <CardDescription>
            Past RCA runs you launched from the Agent Explorer. Stored locally
            in your browser; the agent service itself doesn&apos;t persist
            session ids across restarts.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <form
            className="flex items-center gap-2"
            data-testid="open-by-id-form"
            onSubmit={(e) => {
              e.preventDefault();
              const id = openId.trim();
              if (id) {
                window.location.href = `/incidents/${encodeURIComponent(id)}`;
              }
            }}
          >
            <input
              type="text"
              placeholder="Open a session by id…"
              value={openId}
              onChange={(e) => setOpenId(e.target.value)}
              data-testid="open-by-id-input"
              className="flex-1 rounded border bg-background px-3 py-1.5 text-sm font-mono"
              spellCheck={false}
            />
            <Button type="submit" variant="outline" size="sm" className="gap-1">
              <Search className="h-3 w-3" />
              Open
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm">Recent runs</CardTitle>
          {runs.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              className="h-7 gap-1 text-xs"
              data-testid="clear-history-button"
            >
              <Trash2 className="h-3 w-3" />
              Clear
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <Alert>
              <AlertTitle>No saved runs yet.</AlertTitle>
              <AlertDescription>
                Launch an analysis from the{" "}
                <Link href="/agent-explorer" className="underline">
                  Agent Explorer
                </Link>{" "}
                to populate this list.
              </AlertDescription>
            </Alert>
          ) : (
            <ul className="divide-y" data-testid="recent-runs-list">
              {runs.map((r) => (
                <li
                  key={r.sessionId}
                  className="flex items-center justify-between gap-3 py-2"
                  data-testid="recent-run-item"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-xs text-muted-foreground">
                      {r.sessionId}
                    </div>
                    <div className="truncate text-sm">
                      {r.preview || "(no preview)"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatRelative(r.ts)}
                    </div>
                  </div>
                  <Button asChild variant="outline" size="sm" className="gap-1">
                    <Link href={`/incidents/${encodeURIComponent(r.sessionId)}`}>
                      <ExternalLink className="h-3 w-3" />
                      Open
                    </Link>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
