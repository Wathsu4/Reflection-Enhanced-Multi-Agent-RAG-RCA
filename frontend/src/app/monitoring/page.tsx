"use client";

import { Terminal } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useInvestigationsQueue } from "@/lib/hooks/useInvestigationsQueue";
import { useLogSimulator } from "@/lib/hooks/useLogSimulator";
import type { SimEvent } from "@/lib/types";

import { EventFeed } from "./_components/event-feed";
import { InvestigationsPanel } from "./_components/investigations-panel";
import { LatestEventCard } from "./_components/latest-event-card";
import { SimulatorControls } from "./_components/simulator-controls";
import { SummaryStats } from "./_components/summary-stats";

export default function MonitoringPage() {
  const sim = useLogSimulator();
  // Track which event the user is inspecting. Defaults to the latest.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Auto-follow the latest event whenever a new one arrives, unless the
  // user has explicitly clicked an older row.
  const [followLatest, setFollowLatest] = useState(true);
  useEffect(() => {
    if (followLatest && sim.latest) {
      setSelectedId(sim.latest.id);
    }
  }, [sim.latest, followLatest]);

  const selected: SimEvent | null =
    sim.events.find((e) => e.id === selectedId) ?? sim.latest;

  // Phase 9: auto-RCA queue. The hook pulls classified events out of
  // `sim.events`, dedupes, and runs them sequentially through the
  // ADK pipeline.
  const [autoRcaEnabled, setAutoRcaEnabled] = useState(true);
  const queue = useInvestigationsQueue({
    classifiedEvents: sim.events,
    autoRcaEnabled,
  });

  // Auto-flip to the Investigations tab the FIRST time an investigation
  // appears, so the user notices it without scrolling.
  const [rightTab, setRightTab] = useState<"latest" | "investigations">("latest");
  const [hasAutoFlipped, setHasAutoFlipped] = useState(false);
  useEffect(() => {
    if (hasAutoFlipped) return;
    if (queue.investigations.length > 0) {
      setRightTab("investigations");
      setHasAutoFlipped(true);
    }
  }, [queue.investigations.length, hasAutoFlipped]);

  const handleSelect = (event: SimEvent) => {
    setSelectedId(event.id);
    // If the user clicks the latest event, resume auto-follow; otherwise
    // pin to the chosen row.
    setFollowLatest(event.id === sim.latest?.id);
  };

  const handleClear = () => {
    sim.clear();
    queue.clear();
    setSelectedId(null);
    setFollowLatest(true);
  };

  return (
    <div className="flex flex-1 flex-col gap-4">
      {sim.lastError && (
        <Alert variant="destructive">
          <Terminal className="h-4 w-4" />
          <AlertTitle>Simulator hit an error</AlertTitle>
          <AlertDescription>
            {sim.lastError.message}. The loop will keep running and recover
            once the service is reachable.
          </AlertDescription>
        </Alert>
      )}

      <SummaryStats events={sim.events} />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_1fr_1fr]">
        <SimulatorControls
          running={sim.running}
          options={sim.options}
          eventCount={sim.events.length}
          onStart={() => sim.start()}
          onStop={sim.stop}
          onClear={handleClear}
          onChange={sim.updateOptions}
          autoRcaEnabled={autoRcaEnabled}
          onAutoRcaChange={setAutoRcaEnabled}
        />

        <div className="min-h-[500px]">
          <EventFeed
            events={sim.events}
            selectedId={selected?.id ?? null}
            onSelect={handleSelect}
          />
        </div>

        <div className="flex min-h-[500px] flex-col">
          <Tabs
            value={rightTab}
            onValueChange={(v) => setRightTab(v as typeof rightTab)}
            className="flex flex-1 flex-col"
          >
            <TabsList className="self-start">
              <TabsTrigger value="latest" data-testid="tab-latest">
                Latest event
              </TabsTrigger>
              <TabsTrigger
                value="investigations"
                data-testid="tab-investigations"
                className="gap-2"
              >
                Investigations
                {queue.investigations.length > 0 && (
                  <Badge
                    variant="secondary"
                    className="px-1.5 py-0 text-[10px]"
                  >
                    {queue.investigations.length}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="latest" className="mt-2 flex-1">
              <LatestEventCard event={selected} />
            </TabsContent>
            <TabsContent value="investigations" className="mt-2 flex-1">
              <InvestigationsPanel
                investigations={queue.investigations}
                autoRcaEnabled={autoRcaEnabled}
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
