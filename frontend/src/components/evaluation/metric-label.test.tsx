import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { MetricLabel } from "./metric-label";
import { METRIC_INFO, type MetricKey } from "@/lib/eval/metric-info";

describe("metric-info content", () => {
  it("every metric has a title, what, example, and better blurb", () => {
    const keys = Object.keys(METRIC_INFO) as MetricKey[];
    expect(keys.length).toBeGreaterThanOrEqual(10);
    for (const k of keys) {
      const info = METRIC_INFO[k];
      expect(info.title, k).toBeTruthy();
      expect(info.what.length, k).toBeGreaterThan(20);
      expect(info.example.length, k).toBeGreaterThan(10);
      expect(info.better.length, k).toBeGreaterThan(10);
    }
  });
});

describe("<MetricLabel />", () => {
  it("renders the label text and a tooltip trigger", () => {
    render(
      <TooltipProvider>
        <MetricLabel metricKey="mrr">MRR</MetricLabel>
      </TooltipProvider>,
    );
    expect(screen.getByText("MRR")).toBeInTheDocument();
    expect(screen.getByTestId("metric-label-mrr")).toBeInTheDocument();
  });

  it("falls back to plain children for an unknown key", () => {
    render(
      <TooltipProvider>
        {/* @ts-expect-error intentionally invalid key for the fallback path */}
        <MetricLabel metricKey="not-a-metric">Plain</MetricLabel>
      </TooltipProvider>,
    );
    expect(screen.getByText("Plain")).toBeInTheDocument();
    expect(screen.queryByTestId("metric-label-not-a-metric")).not.toBeInTheDocument();
  });
});
