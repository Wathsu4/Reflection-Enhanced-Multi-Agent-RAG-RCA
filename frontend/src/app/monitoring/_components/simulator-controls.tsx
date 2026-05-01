"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Play, Square, Trash2, ChevronDown } from "lucide-react";
import type { Profile } from "@/lib/types";
import type { SimulatorOptions } from "@/lib/hooks/useLogSimulator";

const PROFILES: Profile[] = ["normal", "warning", "error", "fatal", "mixed"];
const PROFILE_LABEL: Record<Profile, string> = {
  normal: "Healthy traffic",
  warning: "Warnings only",
  error: "Errors only",
  fatal: "Fatal incident",
  mixed: "Mixed (realistic)",
};

export interface SimulatorControlsProps {
  running: boolean;
  options: SimulatorOptions;
  eventCount: number;
  onStart: () => void;
  onStop: () => void;
  onClear: () => void;
  onChange: (overrides: Partial<SimulatorOptions>) => void;
}

export function SimulatorControls({
  running,
  options,
  eventCount,
  onStart,
  onStop,
  onClear,
  onChange,
}: SimulatorControlsProps) {
  return (
    <Card data-testid="simulator-controls">
      <CardHeader>
        <CardTitle className="text-base">Simulator</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label>Profile</Label>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="w-full justify-between"
                disabled={running}
                data-testid="profile-trigger"
              >
                <span>{PROFILE_LABEL[options.profile]}</span>
                <ChevronDown className="h-4 w-4 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56">
              {PROFILES.map((p) => (
                <DropdownMenuItem
                  key={p}
                  onClick={() => onChange({ profile: p })}
                  data-testid={`profile-option-${p}`}
                >
                  {PROFILE_LABEL[p]}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="num-lines">Lines per chunk</Label>
            <span className="text-xs text-muted-foreground">
              {options.numLines}
            </span>
          </div>
          <input
            id="num-lines"
            type="range"
            min={1}
            max={50}
            step={1}
            value={options.numLines}
            onChange={(e) =>
              onChange({ numLines: Number(e.currentTarget.value) })
            }
            disabled={running}
            className="w-full accent-primary"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="interval-ms">Interval (seconds)</Label>
            <span className="text-xs text-muted-foreground">
              {(options.intervalMs / 1000).toFixed(1)}s
            </span>
          </div>
          <input
            id="interval-ms"
            type="range"
            min={500}
            max={10_000}
            step={500}
            value={options.intervalMs}
            onChange={(e) =>
              onChange({ intervalMs: Number(e.currentTarget.value) })
            }
            className="w-full accent-primary"
          />
        </div>

        <div className="flex items-center justify-between rounded-md border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="auto-classify" className="text-sm">
              Auto-classify
            </Label>
            <p className="text-xs text-muted-foreground">
              Run each chunk through the classifier as it is generated.
            </p>
          </div>
          <Switch
            id="auto-classify"
            checked={options.autoClassify}
            onCheckedChange={(c) => onChange({ autoClassify: c })}
            data-testid="auto-classify-switch"
          />
        </div>

        <div className="flex gap-2">
          {running ? (
            <Button
              onClick={onStop}
              variant="destructive"
              className="flex-1"
              data-testid="stop-button"
            >
              <Square className="mr-2 h-4 w-4" /> Stop
            </Button>
          ) : (
            <Button
              onClick={onStart}
              className="flex-1"
              data-testid="start-button"
            >
              <Play className="mr-2 h-4 w-4" /> Start
            </Button>
          )}
          <Button
            onClick={onClear}
            variant="outline"
            disabled={eventCount === 0}
            data-testid="clear-button"
            aria-label="Clear events"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>

        <div className="text-xs text-muted-foreground">
          {eventCount} event{eventCount === 1 ? "" : "s"} captured
        </div>
      </CardContent>
    </Card>
  );
}
