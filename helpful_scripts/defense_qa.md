# Defense Q&A — practice bank

A running list of questions a supervisor / examiner is likely to ask
about this project, together with a rehearsed answer for each.

**How to use this file**

- The **short answer** is the one to actually speak out loud. It's
  written for a non-ML audience and should fit in ~30 seconds.
- The **longer / technical fallback** is what to expand into if the
  examiner pushes for more detail or uses ML jargon.
- **Where this comes from in the code** is for your own reference, so
  you can pull up the file during the defense if needed.
- New questions get **appended at the bottom**, below the marker.
  Keep the same template so the file stays scannable.

## Quick reference: class taxonomy

The classifier maps every chunk of ~30 log lines to one of four
severity labels:

| id | label | meaning |
|---|---|---|
| 0 | `FATAL_OR_CRITICAL` | system crash, unrecoverable error, service down |
| 1 | `ERROR` | recoverable error, exception, 5xx |
| 2 | `WARNING` | degradation signal — latency, retry, deprecation |
| 3 | `NORMAL` | only INFO/DEBUG/TRACE, nothing anomalous |

## Index

1. [Are you labelling the data manually? After preprocessing, is there a separate labelling step?](#q1--are-you-labelling-the-data-manually-after-preprocessing-is-there-a-separate-labelling-step) — added 2026-05-17

---

## Q1 — Are you labelling the data manually? After preprocessing, is there a separate labelling step?

_Tags: data, labels, preprocessing, supervision_

**Short answer (supervisor-friendly):**

> We didn't have anyone manually label the data — the labels were already
> in the dataset itself.
>
> The BGL dataset is a public benchmark of supercomputer logs, and every
> single log line in that dataset already comes tagged with a severity
> word in it, like `INFO`, `WARNING`, `ERROR`, `FATAL`, etc. So our
> "labelling step" is really just a small piece of code that reads that
> existing tag and maps it into one of our four buckets:
> `FATAL_OR_CRITICAL`, `ERROR`, `WARNING`, or `NORMAL`.
>
> Because the classifier looks at a **window of 30 log lines at a time**
> (not individual lines), we apply a simple rule for the window's
> label: if any line inside the window is FATAL, the whole window is
> FATAL; otherwise the worst severity in the window wins.
>
> For the synthetic logs (nginx, Android, web apps, etc.), we generated
> them with a separate small program, and that program writes the label
> directly into the file at the moment of generation — so again, no
> human labelling was needed.
>
> In short: **no manual annotation anywhere in the pipeline.** All
> labels are either inherited from the public dataset or produced
> automatically at the time the data is created.

**Longer / technical fallback (only if they push for ML terms):**

> The formal name for this is **weak supervision via rule-based label
> propagation**. Specifically:
>
> 1. **Per-line label (BGL).** Each raw BGL line has a `Level` token
>    (FATAL / FAILURE / SEVERE / ERROR / WARNING / INFO) and an
>    `alert tag` column ("-" for benign, or an alert category like
>    `KERNDTLB`). A deterministic rule maps those two fields to one of
>    our 4 classes — no learning involved at this stage.
> 2. **Per-chunk label.** We then build 30-line sliding windows
>    (stride 15) and assign each window the worst (most severe) line
>    label inside it. This is a max-pool / OR-style aggregation that
>    matches the operational question we want the model to answer —
>    "does this 2-minute window contain *any* incident worth
>    escalating?"
> 3. **Synthetic data.** Labels are assigned at generation time by the
>    generator program (each generator template knows what severity it
>    is producing). They arrive as JSONL with `{text, label}` already
>    populated.
> 4. **No human-in-the-loop.** There is no manual annotation, no
>    crowd-sourced labelling, no semi-supervised step. The downstream
>    RCA agents also do not produce class labels — the reflection agent
>    emits *relevance deltas* in [-0.2, +0.2] that bias retrieval, which
>    is a different signal entirely.

**Visual demo you can run live:**

```bash
python helpful_scripts/visualize_data_and_labels.py
```

That script prints a few labelled samples per class for each dataset
and writes Markdown summaries into `helpful_scripts/samples/`. It uses
the exact same labelling rule as the training notebook, so it is a
faithful demo of how labels come into existence.

**Where this comes from in the code:**

- `log_severity_classifier_modernbert.ipynb`, Section 3:
  - Cell 6 — `classify_bgl_line()` (the per-line rule)
  - Cell 7 — `create_chunks()` (worst-severity-in-window aggregation)
- `helpful_scripts/visualize_data_and_labels.py` — same logic, runnable
  standalone for demonstration.

---

<!-- ====================================================================== -->
<!-- Append new Q&A blocks below this marker. Copy the template and edit.    -->
<!-- ====================================================================== -->

<!--

## Q{N} — {question phrased the way the examiner would ask it}

_Tags: {comma, separated, tags}_

**Short answer (supervisor-friendly):**

> ...

**Longer / technical fallback (only if they push for ML terms):**

> ...

**Where this comes from in the code:**

- `path/to/file.py` — relevant function / section
- ...

---

-->
