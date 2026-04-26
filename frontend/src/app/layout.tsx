import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import QueryProvider from "@/components/query-provider";
import Link from "next/link";
import {
  LayoutDashboard,
  ScanSearch,
  Activity,
  Bot,
  ClipboardList,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RCA Agent System",
  description:
    "Reflection-Enhanced Multi-Agent RAG for Automated Root-Cause Analysis",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <QueryProvider>
            <div className="grid min-h-screen w-full md:grid-cols-[220px_1fr] lg:grid-cols-[280px_1fr]">
              <aside className="hidden border-r bg-muted/40 md:block">
                <div className="flex h-full max-h-screen flex-col gap-2">
                  <div className="flex h-14 items-center border-b px-4 lg:h-[60px] lg:px-6">
                    <Link
                      href="/"
                      className="flex items-center gap-2 font-semibold"
                    >
                      <Bot className="h-6 w-6" />
                      <span>RCA Agent</span>
                    </Link>
                  </div>
                  <nav className="grid items-start px-2 text-sm font-medium lg:px-4">
                    <Link
                      href="/"
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:text-primary"
                    >
                      <LayoutDashboard className="h-4 w-4" />
                      Dashboard
                    </Link>
                    <Link
                      href="/classify"
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:text-primary"
                    >
                      <ScanSearch className="h-4 w-4" />
                      Classify & RCA
                    </Link>
                    <Link
                      href="/monitoring"
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:text-primary"
                    >
                      <Activity className="h-4 w-4" />
                      Live Monitoring
                    </Link>
                    <Link
                      href="/agent-explorer"
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:text-primary"
                    >
                      <Bot className="h-4 w-4" />
                      Agent Explorer
                    </Link>
                    <Link
                      href="/incidents"
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all hover:text-primary"
                    >
                      <ClipboardList className="h-4 w-4" />
                      Incident History
                    </Link>
                  </nav>
                </div>
              </aside>
              <div className="flex flex-col">
                <header className="flex h-14 items-center gap-4 border-b bg-muted/40 px-4 lg:h-[60px] lg:px-6">
                  <div className="w-full flex-1">
                    <h1 className="text-lg font-semibold">
                      Reflection-Enhanced Multi-Agent RAG
                    </h1>
                  </div>
                  <ThemeToggle />
                </header>
                <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-6">
                  {children}
                </main>
              </div>
            </div>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
