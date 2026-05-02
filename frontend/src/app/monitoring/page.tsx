"use client";

import { useEffect, useState } from "react";
import { useLogSimulator } from "@/lib/hooks/useLogSimulator";
import type { SimEvent } from "@/lib/types";
import { SimulatorControls } from "./_components/simulator-controls";
import { EventFeed } from "./_components/event-feed";
import { LatestEventCard } from "./_components/latest-event-card";
import { SummaryStats } from "./_components/summary-stats";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Terminal } from "lucide-react";

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

  const handleSelect = (event: SimEvent) => {
    setSelectedId(event.id);
    // If the user clicks the latest event, resume auto-follow; otherwise
    // pin to the chosen row.
    setFollowLatest(event.id === sim.latest?.id);
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
          onClear={() => {
            sim.clear();
            setSelectedId(null);
            setFollowLatest(true);
          }}
          onChange={sim.updateOptions}
        />

        <div className="min-h-[500px]">
          <EventFeed
            events={sim.events}
            selectedId={selected?.id ?? null}
            onSelect={handleSelect}
          />
        </div>

        <div className="min-h-[500px]">
          <LatestEventCard event={selected} />
        </div>
      </div>
    </div>
  );
}
