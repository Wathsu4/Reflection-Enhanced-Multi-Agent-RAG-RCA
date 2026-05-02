"use client";

/**
 * Thin wrapper around `react-markdown` configured for our agents'
 * output:
 *
 *   * GitHub-flavoured (tables, task lists, autolinks) -- the agents
 *     emit `## Memory updates` lists with backticked ids, and we want
 *     those to render as code-styled inline.
 *   * No HTML passthrough: we never want to render raw HTML from an
 *     LLM (XSS surface).
 *   * Local prose styling using Tailwind utility classes; we don't pull
 *     in a typography plugin to keep dependency surface small.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

interface MarkdownViewProps {
  markdown: string;
  className?: string;
}

export function MarkdownView({ markdown, className }: MarkdownViewProps) {
  return (
    <div
      className={cn(
        "max-w-none text-sm leading-relaxed",
        // Headings
        "[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-xl [&_h1]:font-semibold",
        "[&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-foreground",
        "[&_h3]:mt-3 [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold",
        // Paragraphs and lists
        "[&_p]:my-2",
        "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5",
        "[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_li]:my-0.5",
        // Inline + block code
        "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em]",
        "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-3",
        "[&_pre>code]:bg-transparent [&_pre>code]:p-0",
        // Blockquotes
        "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-muted-foreground/30 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground",
        // Tables (rare in agent output, but possible)
        "[&_table]:my-2 [&_table]:w-full [&_table]:border-collapse",
        "[&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold",
        "[&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1",
        className,
      )}
      data-testid="markdown-view"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </div>
  );
}
