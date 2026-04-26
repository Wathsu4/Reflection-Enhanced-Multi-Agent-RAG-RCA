import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function MonitoringPage() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Live Monitoring</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            This feature is planned for a future phase. It will simulate a
            real-time log stream to test the classification and RCA pipeline.
          </p>
          <div className="mt-4 text-center text-2xl font-bold">
            Coming in Phase 4
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
