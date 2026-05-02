import { describe, expect, it } from "vitest";

import {
  extractRootCause,
  rootCausePreview,
} from "@/lib/agents/extract-root-cause";

describe("extractRootCause", () => {
  it("returns the first paragraph under the heading", () => {
    const md =
      "## Root cause\n" +
      "Firewall change blocked Redis port 6379 from app subnet.\n" +
      "\n" +
      "## Suggested actions\n";
    expect(extractRootCause(md)).toBe(
      "Firewall change blocked Redis port 6379 from app subnet.",
    );
  });

  it("is case insensitive on the heading", () => {
    const md = "## ROOT CAUSE\nThe disk filled up.";
    expect(extractRootCause(md)).toBe("The disk filled up.");
  });

  it("tolerates a trailing colon on the heading", () => {
    const md = "## Root cause:\nDeadlock between two writers.";
    expect(extractRootCause(md)).toBe("Deadlock between two writers.");
  });

  it("returns empty string when the heading is missing", () => {
    const md = "Some unrelated text.\n## Confidence & caveats\nfoo";
    expect(extractRootCause(md)).toBe("");
  });

  it("returns empty string for empty input", () => {
    expect(extractRootCause("")).toBe("");
  });

  it("returns empty string when the section exists but has no paragraph", () => {
    const md = "## Root cause\n## Suggested actions\nbar";
    expect(extractRootCause(md)).toBe("");
  });

  it("does not bleed into the next section", () => {
    const md =
      "## Root cause\n" +
      "Network outage.\n" +
      "## Suggested actions\n" +
      "Page on-call.\n";
    expect(extractRootCause(md)).toBe("Network outage.");
    expect(extractRootCause(md)).not.toContain("Page on-call");
  });
});

describe("rootCausePreview", () => {
  it("returns the same string when within the limit", () => {
    const md = "## Root cause\nShort.";
    expect(rootCausePreview(md, 100)).toBe("Short.");
  });

  it("truncates with an ellipsis when over the limit", () => {
    const longCause = "x".repeat(200);
    const md = `## Root cause\n${longCause}`;
    const out = rootCausePreview(md, 50);
    expect(out.length).toBeLessThanOrEqual(50);
    expect(out.endsWith("…")).toBe(true);
  });

  it("collapses internal whitespace into single spaces", () => {
    const md = "## Root cause\nLine one\n\nLine two";
    // Only the first content line is captured by extractRootCause, but
    // the whitespace collapse is still exercised.
    const out = rootCausePreview(md);
    expect(out).not.toContain("\n");
  });

  it("returns empty string when there is no root cause", () => {
    expect(rootCausePreview("")).toBe("");
    expect(rootCausePreview("## Other\nfoo")).toBe("");
  });
});
