"use client";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { ParamSpec } from "@/lib/api/evaluation";

export type ParamValues = Record<string, number | boolean>;

/** Build the default value map for a param schema. */
export function defaultParamValues(params: ParamSpec[]): ParamValues {
  const out: ParamValues = {};
  for (const p of params) out[p.name] = p.default;
  return out;
}

/**
 * Renders an experiment's tunable parameters as a small form. Integer
 * params become number inputs (with min/max), booleans become switches.
 * Fully controlled: the parent owns `values`.
 */
export function ParamsForm({
  params,
  values,
  onChange,
  disabled = false,
}: {
  params: ParamSpec[];
  values: ParamValues;
  onChange: (next: ParamValues) => void;
  disabled?: boolean;
}) {
  if (params.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="no-params">
        This experiment takes no parameters.
      </p>
    );
  }

  const set = (name: string, value: number | boolean) =>
    onChange({ ...values, [name]: value });

  return (
    <div className="flex flex-col gap-4" data-testid="params-form">
      {params.map((p) => (
        <div key={p.name} className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor={`param-${p.name}`} className="text-sm">
              {p.label}
            </Label>
            {p.kind === "bool" ? (
              <Switch
                id={`param-${p.name}`}
                data-testid={`param-${p.name}`}
                checked={Boolean(values[p.name])}
                onCheckedChange={(checked) => set(p.name, checked)}
                disabled={disabled}
              />
            ) : (
              <input
                id={`param-${p.name}`}
                data-testid={`param-${p.name}`}
                type="number"
                value={Number(values[p.name])}
                min={p.minimum ?? undefined}
                max={p.maximum ?? undefined}
                disabled={disabled}
                onChange={(e) => set(p.name, Number(e.target.value))}
                className="w-24 rounded border bg-background px-2 py-1 text-right text-sm disabled:opacity-50"
              />
            )}
          </div>
          {p.help && (
            <p className="text-xs text-muted-foreground">{p.help}</p>
          )}
        </div>
      ))}
    </div>
  );
}
