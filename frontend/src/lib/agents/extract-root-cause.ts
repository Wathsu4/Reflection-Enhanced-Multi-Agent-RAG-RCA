/**
 * Heuristics for pulling structured fields out of the final-stage
 * markdown the memory_update_agent emits.
 *
 * The pipeline is prompted to use exactly these section headers:
 *
 *   ## Root cause
 *   ## Suggested actions
 *   ## Confidence & caveats
 *   ## Memory updates
 *
 * In practice Gemini sticks to the format ~95% of the time but
 * occasionally re-orders or relabels. These helpers tolerate light
 * deviation (case, whitespace, inline trailing colons) without
 * resorting to a real markdown parser.
 */

const ROOT_CAUSE_RE = /##\s*Root\s*cause\s*[:\-]?\s*\r?\n+([^\n#]+)/i;

/**
 * Pull the first sentence/paragraph under the `## Root cause` heading.
 *
 * Returns the empty string if the heading isn't found OR the section
 * exists but is empty -- callers can fall back to a placeholder UI
 * label rather than guessing.
 */
export function extractRootCause(markdown: string): string {
  if (!markdown) return "";
  const m = markdown.match(ROOT_CAUSE_RE);
  if (!m) return "";
  return m[1].trim();
}

/**
 * Compact summary line for use in collapsed cards: returns the first
 * `maxChars` characters of the root cause, with a trailing ellipsis if
 * truncated. Single line: collapses internal whitespace.
 */
export function rootCausePreview(markdown: string, maxChars = 120): string {
  const raw = extractRootCause(markdown);
  if (!raw) return "";
  const oneLine = raw.replace(/\s+/g, " ").trim();
  if (oneLine.length <= maxChars) return oneLine;
  return oneLine.slice(0, maxChars - 1).trimEnd() + "…";
}
