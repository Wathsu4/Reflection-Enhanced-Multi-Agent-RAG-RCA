import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

const tools = [
  {
    title: "Classify & RCA",
    href: "/classify",
    description:
      "Triage incoming log data and trigger a root-cause analysis agent for critical issues.",
  },
  {
    title: "Live Monitoring",
    href: "/monitoring",
    description:
      "Simulate a real-time log stream to test the classification and RCA pipeline.",
  },
  {
    title: "Agent Explorer",
    href: "/agent-explorer",
    description:
      "Inspect the internal reasoning and tool usage of the RCA agent for a given session.",
  },
  {
    title: "Incident History",
    href: "/incidents",
    description:
      "Review past automated root-cause analyses and their outcomes.",
  },
];

export default function Home() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {tools.map((tool) => (
          <Card key={tool.href}>
            <CardHeader>
              <CardTitle>{tool.title}</CardTitle>
              <CardDescription>{tool.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Link href={tool.href}>
                <Button className="w-full">
                  Go to {tool.title}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
