import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function IncidentsPage() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Incident History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            This feature is planned for a future phase. It will allow you to
            review past automated root-cause analyses and their outcomes.
          </p>
          <div className="mt-4 text-center text-2xl font-bold">
            Coming in Phase 8
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
