"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { classify } from "@/lib/api/classifier";
import type { ClassifyResponse, Severity } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, Terminal } from "lucide-react";
import {
  ClassifierHttpError,
  ClassifierNetworkError,
} from "@/lib/api/classifier";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ResultCard } from "./_components/result-card";

const logExamples: Record<Severity, string> = {
  NORMAL: `[INFO] 2023-10-27 10:00:00,123 - service-auth - User 'admin' logged in successfully from 192.168.1.100. Session ID: abc-123.`,
  WARNING: `[WARN] 2023-10-27 10:05:14,456 - service-db - Connection pool is reaching its max size. Current: 95/100. Latency for query 'SELECT * FROM users' is 250ms.`,
  ERROR: `[ERROR] 2023-10-27 10:10:22,789 - service-payment - Transaction failed for user 'user@example.com'. Reason: Insufficient funds. Order ID: xyz-789. Exception: PaymentGatewayException.`,
  FATAL_OR_CRITICAL: `[FATAL] 2023-10-27 10:15:30,999 - service-kernel - Core dump initiated. Unhandled segmentation fault at memory address 0xDEADBEEF. The application cannot continue.`,
};

/** Map a thrown error into user-friendly title + body strings. */
function describeError(err: unknown): { title: string; body: string } {
  if (err instanceof ClassifierNetworkError) {
    return {
      title: "Cannot reach classifier service",
      body: "The classifier service did not respond. Make sure it is running on :8001 and that CORS is configured.",
    };
  }
  if (err instanceof ClassifierHttpError) {
    if (err.status >= 500) {
      return {
        title: "Classifier service error",
        body:
          err.detail
            ? `The service returned ${err.status}. Detail: ${err.detail}`
            : `The service returned ${err.status}. Check its server logs.`,
      };
    }
    return {
      title: "Request rejected",
      body: err.detail ?? `The classifier returned ${err.status}.`,
    };
  }
  if (err instanceof Error) return { title: "Error", body: err.message };
  return { title: "Error", body: "An unknown error occurred." };
}

export default function ClassifierPage() {
  const [logChunk, setLogChunk] = useState<string>("");

  const mutation = useMutation<ClassifyResponse, Error, string>({
    mutationFn: classify,
  });

  const handleClassify = () => {
    if (logChunk.trim()) {
      mutation.mutate(logChunk);
    }
  };

  const handleLoadExample = (severity: Severity) => {
    setLogChunk(logExamples[severity]);
    mutation.reset();
  };

  const handleClear = () => {
    setLogChunk("");
    mutation.reset();
  };

  return (
    <div className="container mx-auto p-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column */}
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Log Input</CardTitle>
            </CardHeader>
            <CardContent>
              <Textarea
                placeholder="Paste log lines here..."
                className="min-h-[400px] font-mono"
                value={logChunk}
                onChange={(e) => setLogChunk(e.target.value)}
              />
              <div className="flex items-center gap-2 mt-4">
                <Button
                  onClick={handleClassify}
                  disabled={mutation.isPending || !logChunk.trim()}
                >
                  {mutation.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Classify
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline">Load Example</Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    {Object.keys(logExamples).map((s) => (
                      <DropdownMenuItem
                        key={s}
                        onClick={() => handleLoadExample(s as Severity)}
                      >
                        {s}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button variant="ghost" onClick={handleClear}>
                  Clear
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column */}
        <div className="flex flex-col gap-4">
          <Card className="min-h-[550px]">
            <CardHeader>
              <CardTitle>Classification Result</CardTitle>
            </CardHeader>
            <CardContent>
              {mutation.isIdle && !mutation.data && (
                <div className="text-center text-muted-foreground pt-20">
                  Run a classification to see results.
                </div>
              )}
              {mutation.isPending && (
                <div className="text-center text-muted-foreground pt-20">
                  <Loader2 className="mx-auto h-12 w-12 animate-spin" />
                  <p className="mt-4">Classifying...</p>
                </div>
              )}
              {mutation.isError && (
                <Alert variant="destructive" data-testid="classify-error">
                  <Terminal className="h-4 w-4" />
                  <AlertTitle>{describeError(mutation.error).title}</AlertTitle>
                  <AlertDescription>
                    {describeError(mutation.error).body}
                    <Button
                      variant="link"
                      onClick={handleClassify}
                      className="p-0 h-auto ml-2"
                    >
                      Retry
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
              {mutation.isSuccess && mutation.data && (
                <ResultCard result={mutation.data} />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
