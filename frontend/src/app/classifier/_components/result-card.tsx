import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  SEVERITY_COLORS,
  SEVERITY_ORDER,
  type ClassifyResponse,
} from "@/lib/types";
import { formatConfidence } from "@/lib/utils";
import { cn } from "@/lib/utils";

function SeverityBadge({ severity }: { severity: ClassifyResponse["severity"] }) {
  return (
    <Badge className={cn("text-lg", SEVERITY_COLORS[severity])}>
      {severity.replace(/_/g, " ")}
    </Badge>
  );
}

function PriorityIndicator({ priority }: { priority: ClassifyResponse["priority"] }) {
  const color =
    priority === "critical"
      ? "bg-red-500"
      : priority === "high"
      ? "bg-orange-500"
      : priority === "low"
      ? "bg-yellow-500"
      : "bg-gray-500";
  return (
    <div className="flex items-center gap-2">
      <span className={cn("h-3 w-3 rounded-full", color)}></span>
      <span className="capitalize">{priority}</span>
    </div>
  );
}

export function ResultCard({ result }: { result: ClassifyResponse }) {
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center gap-2">
        <SeverityBadge severity={result.severity} />
        <div className="text-sm text-muted-foreground">Predicted Severity</div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Confidence</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {formatConfidence(result.confidence)}
          </div>
          <Progress value={result.confidence * 100} className="mt-2" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Class Probabilities</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {SEVERITY_ORDER.map((s) => (
              <div key={s} className="flex items-center gap-2">
                <div className="w-32 text-sm capitalize">
                  {s.replace(/_/g, " ").toLowerCase()}
                </div>
                <Progress
                  value={result.all_probabilities[s] * 100}
                  className="flex-1"
                />
                <div className="w-16 text-right text-sm font-mono">
                  {formatConfidence(result.all_probabilities[s])}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <Card>
          <CardHeader>
            <CardDescription>Priority</CardDescription>
          </CardHeader>
          <CardContent>
            <PriorityIndicator priority={result.priority} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Inference Time</CardDescription>
          </CardHeader>
          <CardContent>
            <div>{result.inference_ms.toFixed(2)} ms</div>
          </CardContent>
        </Card>
      </div>

      <Card
        className={cn(
          "p-4 text-center",
          result.should_invoke_rca
            ? "bg-blue-100 dark:bg-blue-900/50"
            : "bg-muted/50"
        )}
      >
        <div className="font-semibold">
          Would trigger RCA pipeline: {result.should_invoke_rca ? "Yes" : "No"}
        </div>
      </Card>
    </div>
  );
}
