/**
 * Integration test for the classifier page error mapping. The page wraps
 * `useMutation` over the `classify` API client, so we mock the client
 * itself \u2014 cheaper and more reliable than mocking `fetch` and waiting
 * for react-query to settle.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import {
  ClassifierHttpError,
  ClassifierNetworkError,
} from "@/lib/api/classifier";

// Hoist the mock so it's wired before the page imports `classify`.
const classifyMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/classifier", async () => {
  const actual = await vi.importActual<
    typeof import("@/lib/api/classifier")
  >("@/lib/api/classifier");
  return {
    ...actual,
    classify: classifyMock,
  };
});

// The page also pulls in the result-card which imports SEVERITY_COLORS \u2014
// no further mocking needed since types/utils are pure.
import ClassifyPage from "./page";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

async function clickClassifyWith(text: string) {
  const user = userEvent.setup();
  const textarea = screen.getByPlaceholderText(/paste log lines here/i);
  await user.clear(textarea);
  await user.type(textarea, text);
  const button = screen.getByRole("button", { name: /^classify$/i });
  await user.click(button);
}

describe("<ClassifyPage /> error handling", () => {
  beforeEach(() => {
    classifyMock.mockReset();
  });

  it("disables the Classify button when input is empty", () => {
    render(<ClassifyPage />, { wrapper: makeWrapper() });

    const button = screen.getByRole("button", { name: /^classify$/i });
    expect(button).toBeDisabled();
  });

  it("renders a friendly message when the classifier service is unreachable", async () => {
    classifyMock.mockRejectedValueOnce(
      new ClassifierNetworkError("could not reach"),
    );

    render(<ClassifyPage />, { wrapper: makeWrapper() });
    await clickClassifyWith("ERROR Connection refused");

    const alert = await screen.findByTestId("classify-error");
    expect(alert).toHaveTextContent(/cannot reach classifier service/i);
    expect(alert).toHaveTextContent(/:8001/);
  });

  it("renders a helpful 5xx message including the server detail", async () => {
    classifyMock.mockRejectedValueOnce(
      new ClassifierHttpError(503, "service error", "classifier not ready"),
    );

    render(<ClassifyPage />, { wrapper: makeWrapper() });
    await clickClassifyWith("ERROR Connection refused");

    const alert = await screen.findByTestId("classify-error");
    expect(alert).toHaveTextContent(/classifier service error/i);
    expect(alert).toHaveTextContent(/503/);
    expect(alert).toHaveTextContent(/classifier not ready/);
  });

  it("renders a 4xx message that surfaces the validation detail", async () => {
    classifyMock.mockRejectedValueOnce(
      new ClassifierHttpError(
        422,
        "rejected",
        "log_chunk must not be empty",
      ),
    );

    render(<ClassifyPage />, { wrapper: makeWrapper() });
    await clickClassifyWith("ERROR Connection refused");

    const alert = await screen.findByTestId("classify-error");
    expect(alert).toHaveTextContent(/request rejected/i);
    expect(alert).toHaveTextContent(/log_chunk must not be empty/);
  });

  it("renders a successful classification result", async () => {
    classifyMock.mockResolvedValueOnce({
      severity: "ERROR",
      severity_id: 1,
      confidence: 0.92,
      should_invoke_rca: true,
      priority: "high",
      inference_ms: 33.4,
      all_probabilities: {
        FATAL_OR_CRITICAL: 0.04,
        ERROR: 0.92,
        WARNING: 0.03,
        NORMAL: 0.01,
      },
    });

    render(<ClassifyPage />, { wrapper: makeWrapper() });
    await clickClassifyWith("ERROR Connection refused");

    await waitFor(() =>
      expect(screen.getByText(/predicted severity/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/would trigger rca pipeline:/i)).toHaveTextContent(
      /yes/i,
    );
  });

  it("triggers a retry when the user clicks the Retry button", async () => {
    classifyMock
      .mockRejectedValueOnce(new ClassifierNetworkError("down"))
      .mockResolvedValueOnce({
        severity: "NORMAL",
        severity_id: 3,
        confidence: 0.99,
        should_invoke_rca: false,
        priority: "none",
        inference_ms: 18,
        all_probabilities: {
          FATAL_OR_CRITICAL: 0.0,
          ERROR: 0.0,
          WARNING: 0.01,
          NORMAL: 0.99,
        },
      });

    render(<ClassifyPage />, { wrapper: makeWrapper() });
    await clickClassifyWith("INFO healthy");
    await screen.findByTestId("classify-error");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(classifyMock).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByText(/predicted severity/i)).toBeInTheDocument(),
    );
  });
});
