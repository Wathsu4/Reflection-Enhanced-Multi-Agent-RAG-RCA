/**
 * Global test setup. Loaded by Vitest before any test file runs.
 *
 * - Adds @testing-library/jest-dom matchers (toBeInTheDocument, etc.)
 * - Polyfills jsdom gaps that Radix UI relies on
 * - Cleans up DOM between tests
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Radix UI's ScrollArea / Tooltip / Popover use ResizeObserver, which jsdom
// does not implement. A no-op stub is sufficient for unit tests that don't
// care about layout measurements.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// Some Radix primitives also call .scrollIntoView on focus.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {};
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
