/**
 * Plain-language explanations for the evaluation metrics, surfaced as
 * hover tooltips in the results view. Each entry answers: what is it, a
 * simple example, and what values are good.
 *
 * Keyed by a stable metric id (not the display label) so labels can change
 * without breaking the mapping.
 */

export interface MetricInfo {
  /** Short human title shown at the top of the tooltip. */
  title: string;
  /** What the metric measures, in plain terms. */
  what: string;
  /** A concrete, simple example reading. */
  example: string;
  /** What values are better / how to read the direction. */
  better: string;
  /** Optional value range, e.g. "0.0–1.0". */
  range?: string;
}

export type MetricKey =
  | "scenarios"
  | "keyword_acc"
  | "keyword_verdict"
  | "keyword_score"
  | "retrieval_recall"
  | "recall_at_k"
  | "mrr"
  | "ndcg"
  | "mean_latency"
  | "latency"
  | "mean_tokens"
  | "tokens"
  | "mean_top_sim"
  | "top_sim"
  | "expected_rank"
  | "llm_judge"
  | "scenario_id";

export const METRIC_INFO: Record<MetricKey, MetricInfo> = {
  scenarios: {
    title: "Scenarios",
    what: "How many test cases (log incidents) were run through the pipeline in this evaluation.",
    example:
      "15 means all 15 curated incidents were evaluated; a smaller number is a limited smoke run.",
    better:
      "Not better or worse — it's the sample size. More scenarios make the averages more trustworthy.",
  },
  keyword_acc: {
    title: "Keyword accuracy (exact + partial)",
    what: "Fraction of scenarios whose answer contained enough of the keywords a domain expert would expect. 'Exact' and 'partial' verdicts both count as a pass.",
    example:
      "0.93 means ~93% of answers mentioned the key terms (e.g. 'redis', 'connection refused', 'firewall').",
    better:
      "Higher is better; 1.0 means every answer hit the expected terms. It's a cheap, deterministic proxy and can't reward correct paraphrases.",
    range: "0.0–1.0",
  },
  keyword_verdict: {
    title: "Verdicts (Exact / Partial / Miss)",
    what: "Per-scenario bucket from keyword overlap: Exact (≥66% of expected keywords present), Partial (≥33%), Miss (<33%).",
    example: "'12 / 2 / 1' means 12 exact, 2 partial, and 1 miss across the scenarios.",
    better: "More Exact and fewer Miss is better.",
  },
  keyword_score: {
    title: "Keyword score (per scenario)",
    what: "The raw keyword-overlap fraction for one scenario: how many of the expected keywords appear in the answer.",
    example: "0.80 means 4 of 5 expected keywords were present.",
    better: "Higher is better; 1.0 means all expected keywords were present.",
    range: "0.0–1.0",
  },
  retrieval_recall: {
    title: "Retrieval recall",
    what: "Across the in-domain scenarios, the fraction where the correct past incident appeared anywhere in the retrieved results.",
    example: "1.0 means the right historical incident was retrieved for every in-domain case.",
    better:
      "Higher is better; low recall means memory search is missing the relevant incident entirely.",
    range: "0.0–1.0",
  },
  recall_at_k: {
    title: "Recall@k",
    what: "Fraction of scenarios where the correct incident is within the top-k retrieved results (k is shown, e.g. 5).",
    example: "Recall@5 = 1.0 means the right incident was always among the top 5 hits.",
    better:
      "Higher is better. With one correct incident per case, 1.0 means perfect top-k coverage.",
    range: "0.0–1.0",
  },
  mrr: {
    title: "MRR (Mean Reciprocal Rank)",
    what: "Average of 1 ÷ (rank of the correct incident). Rewards ranking the right incident near the top, not merely including it.",
    example: "Correct hit at position 1 → 1.0; at 2 → 0.5; at 3 → 0.33. MRR averages this over scenarios.",
    better: "Higher is better; 1.0 means the correct incident was always ranked first.",
    range: "0.0–1.0",
  },
  ndcg: {
    title: "nDCG@k (ranking quality)",
    what: "A normalized ranking score that gives more credit the higher the correct incident is placed. With one relevant item it depends only on that item's rank.",
    example: "Correct hit at rank 1 → 1.0; rank 2 → ~0.63; rank 3 → ~0.50.",
    better: "Higher is better; close to 1.0 means relevant incidents sit at the very top.",
    range: "0.0–1.0",
  },
  mean_latency: {
    title: "Mean latency (seconds)",
    what: "Average wall-clock time to run the full pipeline for one scenario, dominated by the Gemini round-trips.",
    example: "28.3 means each investigation took about 28 seconds end-to-end.",
    better:
      "Lower (faster) is better, but it trades off against doing more reasoning steps (e.g. reflection).",
    range: "seconds",
  },
  latency: {
    title: "Latency (seconds, per scenario)",
    what: "Wall-clock time to run the pipeline for this single scenario.",
    example: "10.9 means this one investigation took ~11 seconds.",
    better: "Lower is faster; deterministic baselines (no LLM) are near-instant.",
    range: "seconds",
  },
  mean_tokens: {
    title: "Mean tokens",
    what: "Average Gemini tokens (input + output) consumed per scenario — a direct proxy for cost.",
    example: "21,000 means each investigation used ~21k tokens across all agent calls.",
    better:
      "Lower is cheaper. More capable variants (full RAG + reflection) tend to use more tokens.",
  },
  tokens: {
    title: "Tokens (per scenario)",
    what: "Gemini tokens (input + output) used for this single scenario across all agent calls.",
    example: "600 means this scenario consumed ~600 tokens; '—' means no LLM call was made.",
    better: "Lower is cheaper.",
  },
  mean_top_sim: {
    title: "Mean top similarity",
    what: "Average cosine similarity (0–1) of the single best retrieved incident to the query — how close the nearest memory match is.",
    example:
      "0.75 means the top match was fairly similar; below ~0.5 suggests no strong match (often an out-of-distribution case).",
    better:
      "Higher means a more confident match. Very low is a useful 'no good match' signal, not necessarily a failure.",
    range: "0.0–1.0",
  },
  top_sim: {
    title: "Top similarity (per scenario)",
    what: "Cosine similarity (0–1) of the best retrieved incident to this scenario's query.",
    example: "0.82 is a strong match; 0.30 suggests nothing relevant was in memory.",
    better: "Higher means a closer match; low values flag out-of-distribution inputs.",
    range: "0.0–1.0",
  },
  expected_rank: {
    title: "Rank of correct incident",
    what: "Position of the correct past incident in the retrieved list for this scenario (1 = top). '—' means it wasn't retrieved or the case is out-of-distribution.",
    example: "1 means the correct incident was the top hit; 3 means it was third.",
    better: "Lower (closer to 1) is better.",
  },
  llm_judge: {
    title: "LLM-as-judge verdict",
    what: "Optional second opinion from Gemini comparing the answer to the ground truth: yes / partial / no (majority of 3 calls).",
    example: "'yes' means the judge agreed the root cause was correct.",
    better: "'yes' is best, then 'partial'. '—' means the judge wasn't run for this evaluation.",
  },
  scenario_id: {
    title: "Scenario id",
    what: "Identifier of the test scenario (incident) from the evaluation dataset.",
    example: "'redis-1' is the first Redis-connection incident variant.",
    better: "Just an identifier — not a metric.",
  },
};
