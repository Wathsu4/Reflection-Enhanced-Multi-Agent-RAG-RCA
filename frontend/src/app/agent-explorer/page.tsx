import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AgentExplorerPage() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Agent Explorer</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            This feature is planned for a future phase. It will allow you to
            inspect the internal reasoning and tool usage of the RCA agent for a
            given session.
          </p>
          <div className="mt-4 text-center text-2xl font-bold">
            Coming in Phase 8
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
