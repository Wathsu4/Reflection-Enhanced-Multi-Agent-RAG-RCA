"use client";

/**
 * Agent Explorer page: paste a log chunk, run the full RCA pipeline,
 * watch the four sub-agents stream their work in real time.
 *
 * Layout: two columns on desktop; the left column owns input + run
 * controls and the right column owns the live timeline. On narrow
 * screens the columns stack.
 */

import {
  AlertCircle,
  Bot,
  Loader2,
  Play,
  Square,
  ChevronDown,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAgentStream } from "@/lib/hooks/useAgentStream";

// Curated log-chunk presets that map cleanly to a seed incident, so the
// out-of-the-box demo always has a strong retrieval hit.
interface ExamplePreset {
  label: string;
  description: string;
  chunk: string;
}

const EXAMPLE_PRESETS: ExamplePreset[] = [
  {
    label: "Redis connection refused",
    description: "Maps to redis-conn-refused-001",
    chunk:
      [
        "2024-01-15 16:30:01 ERROR Failed to connect to Redis at 10.0.1.100:6379 - Connection refused",
        "2024-01-15 16:30:02 INFO  Retrying connection (attempt 1/3)",
        "2024-01-15 16:30:05 ERROR Retry failed: Connection refused",
        "2024-01-15 16:30:06 ERROR Batch job #4521 failed: Cache unavailable",
      ].join("\n"),
  },
  {
    label: "JVM out-of-memory",
    description: "Maps to jvm-oom-heap-001",
    chunk:
      [
        "2024-01-15 22:14:01 FATAL Out of memory: Java heap space - Cannot allocate 512MB",
        "2024-01-15 22:14:01 FATAL JVM terminated. Core dump written to /var/crash/core.4521",
        "2024-01-15 22:14:02 FATAL Service 'order-processor' crashed. PID 4521 exited with signal 9",
        "2024-01-15 22:14:03 ERROR Cascading failure: 3 dependent services unreachable",
      ].join("\n"),
  },
  {
    label: "Postgres deadlock",
    description: "Maps to db-deadlock-001",
    chunk:
      [
        "2024-01-15 11:02:11 ERROR SQLSTATE[40P01]: Deadlock detected",
        "2024-01-15 11:02:11 ERROR Transaction rolled back: deadlock detected (txn_id=84771)",
        "2024-01-15 11:02:13 ERROR Retry attempt 3/3 failed on order update path",
      ].join("\n"),
  },
  {
    label: "TLS certificate expired",
    description: "Maps to tls-cert-expired-001",
    chunk:
      [
        "2024-01-15 00:00:01 ERROR HTTPS handshake failed: certificate verify failed (expired)",
        "2024-01-15 00:00:01 ERROR admin-api health-check failed (connect: error)",
        "2024-01-15 00:00:02 FATAL Maintenance dashboard unreachable -- deploy blocked",
      ].join("\n"),
  },
];

const LAST_RUNS_KEY = "rca:last-sessions";
const LAST_RUNS_LIMIT = 10;

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

function saveLastRun(entry: LastRunEntry): void {
  if (typeof window === "undefined") return;
  const existing = loadLastRuns().filter(
    (r) => r.sessionId !== entry.sessionId,
  );
  const next = [entry, ...existing].slice(0, LAST_RUNS_LIMIT);
  try {
    window.localStorage.setItem(LAST_RUNS_KEY, JSON.stringify(next));
  } catch {
    // Quota exceeded or storage disabled -- nothing actionable.
  }
}

export default function AgentExplorerPage() {
  const [input, setInput] = useState<string>(EXAMPLE_PRESETS[0].chunk);
  const stream = useAgentStream();

  // When a run produces a session id, record it locally so the
  // /incidents page can link to it for replay.
  useEffect(() => {
    if (!stream.sessionId) return;
    if (stream.status !== "streaming" && stream.status !== "done") return;
    saveLastRun({
      sessionId: stream.sessionId,
      preview: input.split("\n")[0]?.slice(0, 120) ?? "",
      ts: Date.now(),
    });
    // Saving is keyed on session id; running effect on any input
    // change would cause spurious writes. So depend strictly on the
    // session id and the terminal state markers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.sessionId, stream.status]);

  const isStreaming = stream.status === "streaming";
  const canRun = !isStreaming && input.trim().length > 0;

  const handleRun = () => {
    if (!canRun) return;
    void stream.run(input.trim());
  };

  const handleRetry = () => {
    stream.reset();
    void stream.run(input.trim());
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[480px_1fr] lg:gap-6">
      {/* ---------- Left column: input & controls ---------- */}
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              Agent Explorer
            </CardTitle>
            <CardDescription>
              Paste a log chunk and run the full retrieval &rarr; reasoning
              &rarr; reflection &rarr; memory-update pipeline. Each agent&apos;s
              work streams in real time on the right.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="log-chunk" className="text-sm">
                Log chunk
              </Label>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 text-xs"
                    data-testid="example-presets-trigger"
                  >
                    Example incidents
                    <ChevronDown className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {EXAMPLE_PRESETS.map((p) => (
                    <DropdownMenuItem
                      key={p.label}
                      onSelect={() => setInput(p.chunk)}
                      className="flex flex-col items-start gap-0.5"
                    >
                      <span className="font-medium">{p.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {p.description}
                      </span>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <Textarea
              id="log-chunk"
              data-testid="log-chunk-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={12}
              placeholder="Paste raw log lines here…"
              spellCheck={false}
              className="font-mono text-xs"
              disabled={isStreaming}
            />

            <div className="flex items-center gap-2">
              <Button
                onClick={handleRun}
                disabled={!canRun}
                data-testid="run-rca-button"
                className="gap-2"
              >
                {isStreaming ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Running…
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Run RCA
                  </>
                )}
              </Button>
              {isStreaming && (
                <Button
                  variant="outline"
                  onClick={stream.cancel}
                  data-testid="cancel-rca-button"
                  className="gap-2"
                >
                  <Square className="h-4 w-4" />
                  Cancel
                </Button>
              )}
              {stream.sessionId && (
                <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                  session {stream.sessionId.slice(0, 8)}
                </span>
              )}
            </div>

            {stream.status === "error" && stream.error && (
              <Alert
                variant="destructive"
                data-testid="run-error-alert"
                className="mt-2"
              >
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>RCA run failed</AlertTitle>
                <AlertDescription className="flex flex-col gap-2">
                  <span className="text-xs">{stream.error}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRetry}
                    className="self-start"
                  >
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Tips</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            <ul className="list-disc space-y-1 pl-4">
              <li>
                A typical run takes 30–60s for four sequential Gemini calls.
              </li>
              <li>
                Cancelling stops further token usage but leaves the partial
                trace on screen.
              </li>
              <li>
                Past sessions are saved locally and viewable on the{" "}
                <Link href="/incidents" className="underline">
                  Incident History
                </Link>{" "}
                page.
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* ---------- Right column: live timeline ---------- */}
      <div className="min-w-0">
        <AgentTimeline
          status={stream.status}
          groups={stream.groups}
          finalMarkdown={stream.finalMarkdown}
        />
      </div>
    </div>
  );
}
